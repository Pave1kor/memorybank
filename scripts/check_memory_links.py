#!/usr/bin/env python3
"""Проверка Memory Bank: целостность Zettelkasten-ссылок + размерный предохранитель
+ сверка каталога команд.

Сканирует `memory-bank/**/*.md` + `CLAUDE.md`.

1. Ссылки. Извлекает `[[name]]` / `[[name#anchor]]`, резолвит `name` по УНИКАЛЬНОМУ
   basename (без расширения) среди `memory-bank/**/*.md`. Печатает нерезолвнутые
   (кроме помеченных `(stub)`) и неоднозначные (несколько файлов с одним basename).
2. Размеры. ТОЛЬКО «хабы» (авто-загружаемые каждую сессию: `CLAUDE.md`, README-роутер,
   `active-context`, `roadmap`) не должны превышать бюджет `(строк, байт)` — предохранитель
   от распухания всегда-платимой поверхности (см. SIZE_BUDGETS). «Спицы» (planned/, per-entity
   заметки, areas/resources, archive/) грузятся по требованию — их размер не ограничивается.
3. Сироты. Спицы (`projects/planned|debts|ideas/*.md`) должны иметь указатель
   `[[basename]]` из своего хаба (`active-context`/`roadmap`) — иначе заметка невидима
   в авто-загружаемом контексте (модель «файл на сущность», см. [[memory-regimen]]).
4. Каталог команд. Двусторонняя сверка
   `memory-bank/resources/commands.md` с фактическим составом: каждый скилл
   (`.claude/skills/*/SKILL.md` + `.claude/skills/*.md`) и каждый `scripts/*.py`
   присутствует в каталоге (первый столбец таблицы, имя в backticks), и наоборот —
   в каталоге нет ghost-записей на несуществующие скиллы/скрипты.

Exit code: 0 — чисто, 1 — есть проблемы (ссылки ИЛИ размер ИЛИ каталог команд).
Только stdlib (pathlib/re/sys) — можно гонять системным python3, venv не нужен.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MEMORY_BANK = REPO_ROOT / "memory-bank"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
COMMANDS_MD = MEMORY_BANK / "resources" / "commands.md"
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
SCRIPTS_DIR = REPO_ROOT / "scripts"

# Строка таблицы вида "| `имя` | ..." — берём первый столбец в backticks.
TABLE_ROW_NAME_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|")

# [[name]] или [[name#anchor]]; name — всё до необязательного #anchor, без ] и #
LINK_RE = re.compile(r"\[\[([^\]#|]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
# признак "не проверять" сразу после ссылки в той же строке
STUB_RE = re.compile(r"\(stub\)")
# inline-code спаны (`...`) — ссылки внутри них не Zettelkasten-ссылки Memory Bank,
# а буквальный текст/синтаксис (напр. `[[id]]` — пример разметки другой фичи)
INLINE_CODE_RE = re.compile(r"`[^`]*`")

# Размерный предохранитель — ТОЛЬКО на «хабах»: файлах, которые платятся контекстом
# в каждой сессии (авто-инъекция харнесса/хука `SessionStart`) или почти-всегда читаются
# как точка входа. «Спицы» (planned/, per-entity долги/идеи, areas/resources, archive/)
# грузятся по требованию через `[[links]]` — их размер не бьёт по каждой сессии, поэтому
# бюджет с них СНЯТ (файл не в SIZE_BUDGETS → не проверяется). Модель «бюджет на хабах»
# зафиксирована 2026-07-09 (атомизация банка). Бюджет = (макс_строк, макс_байт), ~4 байта/токен.
SIZE_BUDGETS: dict[str, tuple[int, int]] = {
    "CLAUDE.md": (350, 22_000),                               # харнесс авто-грузит КАЖДУЮ сессию
    "memory-bank/README.md": (70, 6_000),                     # роутер-карта, грузит хук SessionStart
    "memory-bank/projects/active-context.md": (150, 12_000),  # «сейчас» — точка входа, держим маленьким
    "memory-bank/projects/roadmap.md": (150, 12_000),         # список долгов/идей — триггер атомизации
}


def _code_span_ranges(line: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in INLINE_CODE_RE.finditer(line)]


def _in_code_span(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in spans)


def build_basename_index(md_files: list[Path]) -> dict[str, list[Path]]:
    """basename (без .md) -> список путей с таким basename."""
    index: dict[str, list[Path]] = {}
    for f in md_files:
        key = f.stem
        index.setdefault(key, []).append(f)
    return index


def scan_file(path: Path, index: dict[str, list[Path]]) -> list[str]:
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")
    in_fence = False  # внутри тройного ```-огороженного блока кода
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        code_spans = _code_span_ranges(line)
        for m in LINK_RE.finditer(line):
            if _in_code_span(m.start(), code_spans):
                continue
            name = m.group(1).strip()
            # если сразу после совпадения на той же строке есть "(stub)" — пропуск
            tail = line[m.end():]
            if STUB_RE.match(tail.strip()):
                continue
            candidates = index.get(name)
            if not candidates:
                rel = path.relative_to(REPO_ROOT)
                problems.append(f"{rel}:{lineno}: [[{name}]] unresolved")
            elif len(candidates) > 1:
                rel = path.relative_to(REPO_ROOT)
                paths = ", ".join(str(c.relative_to(REPO_ROOT)) for c in candidates)
                problems.append(f"{rel}:{lineno}: [[{name}]] ambiguous -> [{paths}]")
    return problems


# Спица (каталог) -> хаб, который ОБЯЗАН её перечислять `[[link]]`-указателем. Модель
# «файл на сущность» экономит контекст только если спица достижима из авто-загружаемого
# хаба; забыл указатель — заметка невидима (сирота). Зафиксировано 2026-07-09.
SPOKE_HUB: dict[str, str] = {
    "projects/planned": "projects/active-context.md",
    "projects/debts": "projects/roadmap.md",
    "projects/ideas": "projects/roadmap.md",
}


def links_in_file(path: Path) -> set[str]:
    """Множество `[[name]]`, реально ссылающихся из файла (fence/inline-code пропускаются)."""
    names: set[str] = set()
    if not path.is_file():
        return names
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        spans = _code_span_ranges(line)
        for m in LINK_RE.finditer(line):
            if _in_code_span(m.start(), spans):
                continue
            names.add(m.group(1).strip())
    return names


def check_orphans(md_files: list[Path]) -> list[str]:
    """Спицы (planned/debts/ideas) без указателя `[[basename]]` из своего хаба — сироты."""
    problems: list[str] = []
    hub_links: dict[str, set[str]] = {
        hub: links_in_file(MEMORY_BANK / hub) for hub in set(SPOKE_HUB.values())
    }
    for f in md_files:
        rel = f.relative_to(MEMORY_BANK).as_posix()
        parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
        hub = SPOKE_HUB.get(parent)
        if hub is None:
            continue
        if f.stem not in hub_links[hub]:
            problems.append(
                f"{f.relative_to(REPO_ROOT)}: спица-сирота — нет указателя [[{f.stem}]] "
                f"из хаба {hub} (заметка невидима; добавь строку-указатель или заархивируй)"
            )
    return problems


def check_sizes(files: list[Path]) -> list[str]:
    """Проблемы превышения размерного бюджета (archive/ пропускается)."""
    problems: list[str] = []
    for f in files:
        rel = f.relative_to(REPO_ROOT).as_posix()
        budget = SIZE_BUDGETS.get(rel)
        if budget is None:  # не хаб — бюджет не применяется (спицы грузятся по требованию)
            continue
        data = f.read_bytes()
        nbytes = len(data)
        nlines = data.count(b"\n") + 1
        max_lines, max_bytes = budget
        if nlines > max_lines or nbytes > max_bytes:
            problems.append(
                f"{rel}: {nlines} строк / {nbytes} байт (~{nbytes // 4} токенов) "
                f"> бюджета {max_lines} строк / {max_bytes} байт "
                f"— разбей или заархивируй в archive/"
            )
    return problems


def actual_skill_names() -> set[str]:
    """Имена фактических скиллов: каталоги `.claude/skills/*/SKILL.md` (имя = имя
    каталога) + файлы `.claude/skills/*.md` (имя = basename без .md)."""
    names: set[str] = set()
    if not SKILLS_DIR.is_dir():
        return names
    for entry in SKILLS_DIR.iterdir():
        if entry.is_dir() and (entry / "SKILL.md").is_file():
            names.add(entry.name)
        elif entry.is_file() and entry.suffix == ".md":
            names.add(entry.stem)
    return names


def actual_script_names() -> set[str]:
    """Имена фактических скриптов: `scripts/*.py` (первый уровень, без __pycache__)."""
    names: set[str] = set()
    if not SCRIPTS_DIR.is_dir():
        return names
    for entry in SCRIPTS_DIR.glob("*.py"):
        names.add(entry.name)
    return names


def extract_table_names(text: str, section_header: str) -> set[str]:
    """Имена из первого столбца markdown-таблицы под заголовком `section_header`
    (до следующего заголовка `##`)."""
    lines = text.splitlines()
    names: set[str] = set()
    in_section = False
    for line in lines:
        if line.strip().startswith("## "):
            in_section = line.strip() == section_header
            continue
        if not in_section:
            continue
        m = TABLE_ROW_NAME_RE.match(line.strip())
        if m:
            name = m.group(1).strip()
            if name in ("Скилл", "Скрипт"):  # заголовок таблицы, не запись
                continue
            names.add(name)
    return names


def check_commands_catalog() -> list[str]:
    """Двусторонняя сверка каталога команд с фактическим составом."""
    problems: list[str] = []
    if not COMMANDS_MD.is_file():
        return [f"{COMMANDS_MD.relative_to(REPO_ROOT)}: файл каталога не найден"]

    text = COMMANDS_MD.read_text(encoding="utf-8")
    rel = COMMANDS_MD.relative_to(REPO_ROOT)

    # --- Скиллы ---
    catalog_skills = extract_table_names(text, "## Скиллы")
    actual_skills = actual_skill_names()
    missing_skills = actual_skills - catalog_skills
    ghost_skills = catalog_skills - actual_skills
    for name in sorted(missing_skills):
        problems.append(f"{rel}: скилл `{name}` существует, но не внесён в каталог (секция «Скиллы»)")
    for name in sorted(ghost_skills):
        problems.append(f"{rel}: каталог ссылается на несуществующий скилл `{name}` (ghost-запись)")

    # --- Скрипты ---
    catalog_scripts = extract_table_names(text, "## Скрипты")
    actual_scripts = actual_script_names()
    # в каталоге имена даны как "scripts/<name>.py" — нормализуем к basename
    catalog_script_basenames = {
        name.rsplit("/", 1)[-1] for name in catalog_scripts if name.endswith(".py")
    }
    missing_scripts = actual_scripts - catalog_script_basenames
    ghost_scripts = catalog_script_basenames - actual_scripts
    for name in sorted(missing_scripts):
        problems.append(f"{rel}: скрипт `scripts/{name}` существует, но не внесён в каталог (секция «Скрипты»)")
    for name in sorted(ghost_scripts):
        problems.append(f"{rel}: каталог ссылается на несуществующий скрипт `scripts/{name}` (ghost-запись)")

    return problems


def main() -> int:
    if not MEMORY_BANK.is_dir():
        print(f"memory-bank not found at {MEMORY_BANK}", file=sys.stderr)
        return 1

    md_files = sorted(MEMORY_BANK.rglob("*.md"))
    index = build_basename_index(md_files)

    scan_targets = list(md_files)
    if CLAUDE_MD.is_file():
        scan_targets.append(CLAUDE_MD)

    link_problems: list[str] = []
    for f in scan_targets:
        link_problems.extend(scan_file(f, index))

    size_problems = check_sizes(scan_targets)
    orphan_problems = check_orphans(md_files)
    catalog_problems = check_commands_catalog()

    if link_problems or size_problems or orphan_problems or catalog_problems:
        if link_problems:
            print(f"Проблемы со ссылками: {len(link_problems)}")
            for p in link_problems:
                print(f"  {p}")
        if size_problems:
            print(f"Превышение размерного бюджета: {len(size_problems)}")
            for p in size_problems:
                print(f"  {p}")
        if orphan_problems:
            print(f"Спицы-сироты (нет указателя из хаба): {len(orphan_problems)}")
            for p in orphan_problems:
                print(f"  {p}")
        if catalog_problems:
            print(f"Рассинхрон каталога команд: {len(catalog_problems)}")
            for p in catalog_problems:
                print(f"  {p}")
        return 1

    print(
        f"OK: проверено файлов {len(scan_targets)}, "
        f"ссылки целы, размеры в бюджете."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
