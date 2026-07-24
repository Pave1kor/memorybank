#!/usr/bin/env python3
"""Recall-CLI поверх Memory Bank — shortlist релевантных заметок по запросу.

Производный лексический индекс живых заметок `memory-bank/**/*.md` (кроме
`archive/`) + сабкоманды:

- `query "<текст>"` — top-k заметок по запросу (веса полей + 1-hop link-boost).
- `atomize-signal` — кандидаты на атомизацию: спицы за бюджетом объёма
  (`SPOKE_MAX_LINES`/`SPOKE_MAX_KB`) + хабы с толстыми инлайн-секциями без
  указателя на спицу (`HUB_SECTION_MAX_LINES`). Хабы — `memory-bank/README.md`,
  `memory-bank/projects/active-context.md`, `memory-bank/projects/roadmap.md`
  (см. `HUB_PATHS`, согласовано с `memory-regimen.md`). `CLAUDE.md` — тоже хаб
  по регламенту, но лежит ВНЕ `memory-bank/` и этим индексом НЕ сканируется
  (его бюджет проверяет отдельно `check_memory_links.py`).
- `rebuild` — принудительная пересборка индекса (диагностика).

Индекс — `memory-bank/.recall-index.json`, gitignored, производный, ВСЕГДА
воспроизводим из заметок; инвалидация прозрачна (состав/mtime файлов,
версия схемы) — повреждение/устаревание НИКОГДА не ошибка пользователю.

Только stdlib (pathlib/re/json/argparse/unicodedata); НИКАКИХ импортов
кода приложения — инструмент изолирован, работает любым `python3`/`py` без venv.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# ─── Принудительный UTF-8 stdout/stderr (Windows cp1251-консоль не должна
# падать на кириллице/emoji). Инструмент изолирован от кода приложения —
# локальная копия паттерна, без внешних импортов. ───
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


# ═══════════════════════════════════════════════════════════════════════════
# Константы (единый блок, ничего "по коду")
# ═══════════════════════════════════════════════════════════════════════════

REPO_ROOT = Path(__file__).resolve().parent.parent
MEMORY_BANK = REPO_ROOT / "memory-bank"
INDEX_PATH = MEMORY_BANK / ".recall-index.json"

INDEX_VERSION = 1  # несовпадение с версией в файле индекса -> молчаливая пересборка
ARCHIVE_SEGMENT = "archive"  # первый сегмент пути внутри memory-bank/, исключаемый по умолчанию

TOP_K = 5  # дефолт размера выдачи query (--k переопределяет)

# Веса совпадений по полям (data-model.md) — специфичные поля весят больше,
# общий мешок терминов (terms) — слабый fallback-сигнал.
W_SLUG = 5
W_TITLE = 4
W_DESC = 3
W_HEAD = 2
W_TERM = 1

LINK_BOOST = 0.5  # множитель добавки 1-hop соседу от score источника

DESCRIPTION_MAX_CHARS = 200  # обрезка вводного абзаца для description/reason

# Бюджеты atomize-signal (порог размера спицы для сигнала атомизации).
SPOKE_MAX_LINES = 250
SPOKE_MAX_KB = 25
HUB_SECTION_MAX_LINES = 15

# Хабы (авто-загружаемые КАЖДУЮ сессию — memory-regimen.md): единственные записи,
# проверяемые на hub-fat-section; всё остальное — спицы (spoke-over-budget), у них
# разные критерии (data-model.md AtomizeCandidate). Синхронизировано со SIZE_BUDGETS
# в `check_memory_links.py`, минус `CLAUDE.md` — тот лежит вне memory-bank/ и этим
# индексом не сканируется (см. докстринг модуля).
HUB_PATHS = frozenset({
    "memory-bank/README.md",
    "memory-bank/projects/active-context.md",
    "memory-bank/projects/roadmap.md",
})

# Сабкоманды, известные CLI (для распознавания "дефолтной" query без явного слова).
KNOWN_COMMANDS = {"query", "rebuild", "atomize-signal"}
# Флаги, потребляющие следующий токен как значение (форма `--k 5`). Нужны
# _normalize_argv, чтобы значение флага не приняли за «первый позиционный» (текст запроса).
VALUE_FLAGS = {"--k"}


# ═══════════════════════════════════════════════════════════════════════════
# Регексы разбора Markdown (тот же дух, что `check_memory_links.py`: пропуск
# fenced-блоков ``` и inline-code `...` — примеры синтаксиса в тексте банка
# не должны читаться как реальные ссылки/заголовки/bold-термины)
# ═══════════════════════════════════════════════════════════════════════════

LINK_RE = re.compile(r"\[\[([^\]#|]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
WORD_RE = re.compile(r"\w+", re.UNICODE)
INLINE_CODE_RE = re.compile(r"`[^`]*`")


def _code_span_ranges(line: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in INLINE_CODE_RE.finditer(line)]


def _in_code_span(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in spans)


# ═══════════════════════════════════════════════════════════════════════════
# Схема (data-model.md) — ОДИН авторитетный источник для build_index/query
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class IndexEntry:
    path: str            # POSIX-относительный от корня репо; PK
    slug: str             # basename без .md; уникален в банке
    category: str         # projects | areas | resources | hub | archive
    title: str             # первый `# `-заголовок; фолбэк — slug
    description: str        # вводный абзац/HTML-комментарий под заголовком; "" если нет
    headings: list[str]      # все ##/### заголовки по порядку
    terms: list[str]          # нормализованные токены title+headings+**bold**
    links_out: list[str]       # слаги из [[name]]/[[name#anchor]] тела
    links_in: list[str]         # обратные ссылки (вычисляются на сборке)
    lines: int                   # число строк файла
    bytes: int                    # размер файла
    mtime: float                   # st_mtime на момент сборки


@dataclass
class IndexFile:
    version: int
    built_at: str                    # ISO-8601, информативное
    files: dict                       # {path: mtime} — снимок живых файлов, ключ инвалидации
    entries: list = field(default_factory=list)  # list[IndexEntry], отсортированы по path


@dataclass
class RecallHit:
    path: str
    score: float
    description: str
    reason: str


@dataclass
class AtomizeCandidate:
    path: str
    reason: str  # "spoke-over-budget (NNN строк / NN КБ)" | "hub-fat-section («…», NN строк)"


class SlugCollisionError(Exception):
    """Дубль slug при сборке индекса — ошибка со списком коллизий (не молчаливый выбор одного)."""

    def __init__(self, collisions: dict) -> None:
        self.collisions = collisions
        detail = "; ".join(
            f"{slug}: {', '.join(paths)}" for slug, paths in sorted(collisions.items())
        )
        super().__init__(f"Коллизия slug при сборке индекса: {detail}")


# ═══════════════════════════════════════════════════════════════════════════
# Нормализация токенов (lowercase, NFC, кириллица+латиница наравне)
# ═══════════════════════════════════════════════════════════════════════════

def tokenize(text: str) -> list[str]:
    """Слова text -> lowercase NFC-нормализованные токены (порядок появления, без дублей)."""
    normalized = unicodedata.normalize("NFC", text)
    tokens: list[str] = []
    seen = set()
    for m in WORD_RE.finditer(normalized):
        tok = m.group(0).lower()
        if tok not in seen:
            seen.add(tok)
            tokens.append(tok)
    return tokens


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip() + "…"


# ═══════════════════════════════════════════════════════════════════════════
# Разбор одной заметки
# ═══════════════════════════════════════════════════════════════════════════

def _clean_description(raw: str) -> str:
    raw = raw.strip()
    if len(raw) > 1 and raw.startswith("_") and raw.endswith("_"):
        raw = raw[1:-1].strip()
    raw = BOLD_RE.sub(r"\1", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return _truncate(raw, DESCRIPTION_MAX_CHARS)


def _extract_title_and_description(lines: list[str]) -> tuple[str | None, str]:
    title = None
    title_idx = None
    for i, line in enumerate(lines):
        m = re.match(r"^#\s+(.+?)\s*$", line)
        if m:
            title = m.group(1).strip()
            title_idx = i
            break
    if title_idx is None:
        return None, ""

    i = title_idx + 1
    n = len(lines)
    while i < n and lines[i].strip() == "":
        i += 1
    if i >= n or lines[i].lstrip().startswith("#"):
        return title, ""

    if lines[i].strip().startswith("<!--"):
        buf = []
        while i < n and "-->" not in lines[i]:
            buf.append(lines[i])
            i += 1
        if i < n:
            buf.append(lines[i])
        raw = " ".join(buf).replace("<!--", "").replace("-->", "")
        return title, _clean_description(raw)

    buf = []
    while i < n and lines[i].strip() != "" and not lines[i].lstrip().startswith("#"):
        buf.append(lines[i].strip())
        i += 1
    return title, _clean_description(" ".join(buf))


def _extract_headings(lines: list[str]) -> list[str]:
    headings = []
    in_fence = False
    for line in lines:
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r"^(#{2,3})\s+(.+?)\s*$", line)
        if m:
            headings.append(m.group(2).strip())
    return headings


def _extract_bold_terms(lines: list[str]) -> list[str]:
    bold = []
    in_fence = False
    for line in lines:
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        spans = _code_span_ranges(line)
        for m in BOLD_RE.finditer(line):
            if _in_code_span(m.start(), spans):
                continue
            bold.append(m.group(1))
    return bold


def _extract_links_out(lines: list[str]) -> list[str]:
    links: list[str] = []
    seen = set()
    in_fence = False
    for line in lines:
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        spans = _code_span_ranges(line)
        for m in LINK_RE.finditer(line):
            if _in_code_span(m.start(), spans):
                continue
            name = m.group(1).strip()
            if name not in seen:
                seen.add(name)
                links.append(name)
    return links


def _extract_terms(title: str | None, headings: list[str], bold_terms: list[str]) -> list[str]:
    tokens: list[str] = []
    seen = set()
    for part in ([title] if title else []) + headings + bold_terms:
        for tok in tokenize(part):
            if tok not in seen:
                seen.add(tok)
                tokens.append(tok)
    return tokens


def parse_note(path: Path, memory_bank: Path, repo_root: Path) -> IndexEntry:
    """Один живой .md-файл банка -> IndexEntry (links_in пуст — считается на сборке)."""
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        # Одна заметка с битой кодировкой не должна ронять весь build_index —
        # индексируем с заменой невалидных байт и предупреждаем в stderr.
        print(f"warn: заметка с некорректной кодировкой, индексируется с заменой: "
              f"{path} ({exc})", file=sys.stderr)
        raw = path.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()
    stat = path.stat()

    rel_to_bank = path.relative_to(memory_bank)
    parts = rel_to_bank.parts
    category = "hub" if len(parts) == 1 else parts[0]

    title, description = _extract_title_and_description(lines)
    headings = _extract_headings(lines)
    bold_terms = _extract_bold_terms(lines)
    terms = _extract_terms(title, headings, bold_terms)
    links_out = _extract_links_out(lines)

    return IndexEntry(
        path=path.relative_to(repo_root).as_posix(),
        slug=path.stem,
        category=category,
        title=title or path.stem,
        description=description,
        headings=headings,
        terms=terms,
        links_out=links_out,
        links_in=[],
        lines=len(lines),
        bytes=stat.st_size,
        mtime=stat.st_mtime,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Сборка индекса + инвалидация
# ═══════════════════════════════════════════════════════════════════════════

def iter_bank_files(memory_bank: Path, *, include_archive: bool = False) -> list[Path]:
    files = []
    if not memory_bank.is_dir():
        return files
    for f in sorted(memory_bank.rglob("*.md")):
        if not include_archive:
            rel_parts = f.relative_to(memory_bank).parts
            if rel_parts and rel_parts[0] == ARCHIVE_SEGMENT:
                continue
        files.append(f)
    return files


def snapshot_files(memory_bank: Path, repo_root: Path, *, include_archive: bool = False) -> dict:
    """{POSIX-relative-от-repo-root path: mtime} живых .md — дешёвый ключ инвалидации."""
    return {
        f.relative_to(repo_root).as_posix(): f.stat().st_mtime
        for f in iter_bank_files(memory_bank, include_archive=include_archive)
    }


def compute_links_in(entries: list) -> None:
    """Мутирует entries: заполняет links_in обратными ссылками из links_out.
    [[link]] на несуществующий slug -> warning в stderr (индекс собирается)."""
    by_slug = {e.slug: e for e in entries}
    incoming: dict = {e.slug: [] for e in entries}
    for e in entries:
        for target_slug in e.links_out:
            target = by_slug.get(target_slug)
            if target is None:
                print(
                    f"warning: [[{target_slug}]] в {e.path} не резолвится (broken link)",
                    file=sys.stderr,
                )
                continue
            if e.slug not in incoming[target.slug]:
                incoming[target.slug].append(e.slug)
    for e in entries:
        e.links_in = sorted(incoming[e.slug])


def build_index(memory_bank: Path = MEMORY_BANK, repo_root: Path = REPO_ROOT, *, include_archive: bool = False) -> IndexFile:
    """Полная пересборка индекса: сканирует живые заметки, парсит, проверяет
    уникальность slug (коллизия -> SlugCollisionError), считает links_in."""
    files = iter_bank_files(memory_bank, include_archive=include_archive)
    entries = [parse_note(f, memory_bank, repo_root) for f in files]

    slug_to_paths: dict = {}
    for e in entries:
        slug_to_paths.setdefault(e.slug, []).append(e.path)
    collisions = {slug: paths for slug, paths in slug_to_paths.items() if len(paths) > 1}
    if collisions:
        raise SlugCollisionError(collisions)

    compute_links_in(entries)
    entries.sort(key=lambda e: e.path)

    return IndexFile(
        version=INDEX_VERSION,
        built_at=datetime.now(timezone.utc).isoformat(),
        files={e.path: e.mtime for e in entries},
        entries=entries,
    )


def save_index(index_file: IndexFile, path: Path) -> None:
    payload = {
        "version": index_file.version,
        "built_at": index_file.built_at,
        "files": index_file.files,
        "entries": [asdict(e) for e in index_file.entries],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_index(path: Path) -> IndexFile | None:
    """None при отсутствии/повреждении файла — прозрачная пересборка, НИКОГДА ошибка."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = [IndexEntry(**e) for e in data["entries"]]
        return IndexFile(version=data["version"], built_at=data["built_at"], files=data["files"], entries=entries)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def load_or_build_index(memory_bank: Path = MEMORY_BANK, repo_root: Path = REPO_ROOT, index_path: Path = INDEX_PATH) -> IndexFile:
    """Прозрачная инвалидация: version + снимок {path:mtime} живых файлов
    (без archive/ — единственный персистентный вариант кэша)."""
    cached = load_index(index_path)
    if cached is not None and cached.version == INDEX_VERSION:
        current_snapshot = snapshot_files(memory_bank, repo_root)
        if current_snapshot == cached.files:
            return cached
    fresh = build_index(memory_bank, repo_root)
    save_index(fresh, index_path)
    return fresh


# ═══════════════════════════════════════════════════════════════════════════
# query: скоринг + 1-hop link-boost
# ═══════════════════════════════════════════════════════════════════════════

def _first_matching_heading(headings: list[str], matched_tokens: set) -> str | None:
    for h in headings:
        if set(tokenize(h)) & matched_tokens:
            return h
    return None


def score_entry(query_tokens: list[str], entry: IndexEntry) -> tuple[float, list[str]]:
    """Score/reason одной записи по весам полей (независимые поля, суммируются)."""
    qset = set(query_tokens)
    score = 0.0
    reasons: list[str] = []

    slug_tokens = set(tokenize(entry.slug.replace("-", " ").replace("_", " ")))
    matched = qset & slug_tokens
    if matched:
        score += W_SLUG * len(matched)
        reasons.append(f"slug:{entry.slug}")

    title_tokens = set(tokenize(entry.title))
    matched = qset & title_tokens
    if matched:
        score += W_TITLE * len(matched)
        reasons.append(f"title:{_truncate(entry.title, 60)}")

    desc_tokens = set(tokenize(entry.description))
    matched = qset & desc_tokens
    if matched:
        score += W_DESC * len(matched)
        reasons.append(f"desc:{_truncate(entry.description, 40)}")

    heading_tokens = set(tokenize(" ".join(entry.headings)))
    matched = qset & heading_tokens
    if matched:
        score += W_HEAD * len(matched)
        heading = _first_matching_heading(entry.headings, matched)
        if heading:
            reasons.append(f"heading:«{heading}»")

    term_tokens = set(entry.terms)
    matched = qset & term_tokens
    if matched:
        score += W_TERM * len(matched)
        reasons.append(f"term:{','.join(sorted(matched))}")

    return score, reasons


def query_index(index_file: IndexFile, query_text: str, k: int = TOP_K) -> list:
    query_tokens = tokenize(query_text)
    if not query_tokens:
        return []

    entries_by_slug = {e.slug: e for e in index_file.entries}
    scored: dict = {}
    for e in index_file.entries:
        score, reasons = score_entry(query_tokens, e)
        if score > 0:
            scored[e.slug] = (score, reasons)

    # 1-hop link-boost: сосед (links_out ИЛИ links_in) сильного совпадения получает
    # LINK_BOOST x score источника; при нескольких кандидатах-источниках — лучший.
    boosts: dict = {}
    for slug, (score, _reasons) in list(scored.items()):
        source_entry = entries_by_slug[slug]
        neighbor_slugs = set(source_entry.links_out) | set(source_entry.links_in)
        for neighbor_slug in neighbor_slugs:
            if neighbor_slug not in entries_by_slug or neighbor_slug == slug:
                continue
            boost_value = LINK_BOOST * score
            if neighbor_slug not in boosts or boost_value > boosts[neighbor_slug][0]:
                boosts[neighbor_slug] = (boost_value, slug)

    for neighbor_slug, (boost_value, source_slug) in boosts.items():
        reason = f"link:[[{source_slug}]]"
        if neighbor_slug in scored:
            existing_score, existing_reasons = scored[neighbor_slug]
            scored[neighbor_slug] = (existing_score + boost_value, existing_reasons + [reason])
        else:
            scored[neighbor_slug] = (boost_value, [reason])

    hits = [
        RecallHit(
            path=entries_by_slug[slug].path,
            score=round(score, 4),
            description=entries_by_slug[slug].description or entries_by_slug[slug].title,
            reason=", ".join(reasons),
        )
        for slug, (score, reasons) in scored.items()
    ]
    hits.sort(key=lambda h: (-h.score, h.path))
    return hits[:k]


# ═══════════════════════════════════════════════════════════════════════════
# atomize-signal: бюджет спиц (агрегатный объём) + толстые инлайн-секции хабов
# (US3, T010). Пороги — ТОЛЬКО из блока констант выше; хаб/спица различаются
# по HUB_PATHS, критерии не смешиваются (data-model.md AtomizeCandidate).
# ═══════════════════════════════════════════════════════════════════════════

_H2_HEADING_RE = re.compile(r"^##(?!#)\s+(.+?)\s*$")  # ровно уровень 2, не ### и не #


def _hub_sections(lines: list[str]) -> list[tuple[str, list[str]]]:
    """(heading, content_lines) для каждой H2-секции файла. Содержимое — строки
    между заголовками (или до EOF); fenced-блоки (```) не разбивают секцию —
    код внутри остаётся частью содержимого, как в остальных парсерах модуля."""
    sections: list[tuple[str, list[str]]] = []
    heading: str | None = None
    content: list[str] = []
    in_fence = False
    for line in lines:
        if line.strip().startswith("```"):
            in_fence = not in_fence
            if heading is not None:
                content.append(line)
            continue
        if not in_fence:
            m = _H2_HEADING_RE.match(line)
            if m:
                if heading is not None:
                    sections.append((heading, content))
                heading = m.group(1).strip()
                content = []
                continue
        if heading is not None:
            content.append(line)
    if heading is not None:
        sections.append((heading, content))
    return sections


def _hub_fat_section_candidates(entry: IndexEntry, repo_root: Path) -> list:
    """Хаб: H2-секции > HUB_SECTION_MAX_LINES строк БЕЗ единой [[link]]-ссылки —
    контент, который стоило вынести в спицу с указателем, а не расписать инлайн.
    Секция хотя бы с одним [[link]] считается уже размеченной указателями (не
    "толстым инлайном"), даже если формально длинная."""
    full_path = repo_root / entry.path
    try:
        lines = full_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    candidates = []
    for heading, content in _hub_sections(lines):
        if len(content) > HUB_SECTION_MAX_LINES and not _extract_links_out(content):
            reason = f"hub-fat-section («{heading}», {len(content)} строк)"
            candidates.append(AtomizeCandidate(path=entry.path, reason=reason))
    return candidates


def atomize_signal(index_file: IndexFile, repo_root: Path = REPO_ROOT) -> list:
    """Кандидаты на атомизацию: спицы за агрегатным бюджетом строк/КБ + хабы с
    толстыми инлайн-секциями. Разные критерии для хаба и спицы (см. HUB_PATHS) —
    хаб никогда не получает spoke-over-budget, спица никогда не проверяется
    посекционно. Сортировка (path, reason) — детерминизм."""
    candidates: list = []
    for e in index_file.entries:
        if e.path in HUB_PATHS:
            candidates.extend(_hub_fat_section_candidates(e, repo_root))
        else:
            kb = e.bytes / 1024
            if e.lines > SPOKE_MAX_LINES or kb > SPOKE_MAX_KB:
                reason = f"spoke-over-budget ({e.lines} строк / {round(kb)} КБ)"
                candidates.append(AtomizeCandidate(path=e.path, reason=reason))
    candidates.sort(key=lambda c: (c.path, c.reason))
    return candidates


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def _normalize_argv(argv: list[str]) -> list[str]:
    """query — дефолтная сабкоманда: если первый позиционный токен не входит
    в KNOWN_COMMANDS, трактуем его как текст запроса (вставляем "query").

    Значение value-флага в раздельной форме (`--k 5`) НЕ считается позиционным —
    иначе для `mb_recall.py --k 5 текст` первым «позиционным» окажется `5`. "query"
    вставляется В НАЧАЛО (не перед первым позиционным): все флаги (`--k`/`--json`/…)
    принадлежат субпарсеру `query` и argparse требует их ПОСЛЕ имени сабкоманды."""
    first_positional = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("-"):
            # `--k 5` (раздельная форма) съедает следующий токен как значение;
            # `--k=5` самодостаточен и следующий токен не потребляет.
            if a in VALUE_FLAGS and "=" not in a:
                i += 2
            else:
                i += 1
            continue
        first_positional = i
        break
    if first_positional is None or argv[first_positional] in KNOWN_COMMANDS:
        return argv
    return ["query", *argv]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mb_recall.py", description="Context Fabric recall поверх Memory Bank")
    sub = parser.add_subparsers(dest="command")

    query_parser = sub.add_parser("query", help="top-k заметок по запросу")
    query_parser.add_argument("text", nargs="?", default=None, help="текст запроса")
    query_parser.add_argument("--k", type=int, default=TOP_K)
    query_parser.add_argument("--json", action="store_true")
    query_parser.add_argument("--include-archive", action="store_true")

    atomize_parser = sub.add_parser("atomize-signal", help="кандидаты на атомизацию (толстые спицы/хабы)")
    atomize_parser.add_argument("--json", action="store_true")

    sub.add_parser("rebuild", help="принудительная пересборка индекса")

    return parser


def _cmd_query(args: argparse.Namespace) -> int:
    text = (args.text or "").strip()
    if not text:
        print(
            'Ошибка: пустой запрос. Использование: mb_recall.py query "<текст>" [--k N] [--json]',
            file=sys.stderr,
        )
        return 2

    try:
        if args.include_archive:
            index_file = build_index(MEMORY_BANK, REPO_ROOT, include_archive=True)
        else:
            index_file = load_or_build_index(MEMORY_BANK, REPO_ROOT, INDEX_PATH)
    except SlugCollisionError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    hits = query_index(index_file, text, k=args.k)

    if args.json:
        print(json.dumps({"query": text, "hits": [asdict(h) for h in hits]}, ensure_ascii=False))
    else:
        if not hits:
            print("(пусто — нет совпадений)")
        for h in hits:
            print(f"{h.path} — {h.description} (score {h.score}; {h.reason})")
    return 0


def _cmd_atomize_signal(args: argparse.Namespace) -> int:
    try:
        index_file = load_or_build_index(MEMORY_BANK, REPO_ROOT, INDEX_PATH)
    except SlugCollisionError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    candidates = atomize_signal(index_file, REPO_ROOT)

    if args.json:
        print(json.dumps({"candidates": [asdict(c) for c in candidates]}, ensure_ascii=False))
    else:
        if not candidates:
            print("(пусто — кандидатов на атомизацию нет)")
        for c in candidates:
            print(f"{c.path} — {c.reason}")
    return 1 if candidates else 0


def _cmd_rebuild(_args: argparse.Namespace) -> int:
    try:
        index_file = build_index(MEMORY_BANK, REPO_ROOT)
    except SlugCollisionError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    save_index(index_file, INDEX_PATH)
    print(f"OK: индекс пересобран — {INDEX_PATH} ({len(index_file.entries)} записей)")
    return 0


def main(argv: list[str] | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else argv
    parser = build_arg_parser()
    args = parser.parse_args(_normalize_argv(raw_argv))

    if args.command is None:
        parser.print_usage(sys.stderr)
        print("mb_recall.py: требуется сабкоманда (query | atomize-signal | rebuild)", file=sys.stderr)
        return 2
    if args.command == "query":
        return _cmd_query(args)
    if args.command == "atomize-signal":
        return _cmd_atomize_signal(args)
    if args.command == "rebuild":
        return _cmd_rebuild(args)

    parser.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
