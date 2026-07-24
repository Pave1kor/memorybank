# Memory Bank Framework

Переиспользуемый каркас «как работать с Claude Code»: правила проекта (`CLAUDE.md`),
файловая база знаний **Memory Bank** (PARA + Zettelkasten), команды-скиллы (`/flow`, `/status`,
`/publish`, `/checkpoint`, `/debt`, …), мультиагентный ревью-каскад `/ca-review` и speckit-цикл.
Домен-нейтральный — вычищен от любой проектной специфики, подключается в любой проект.

## Что внутри

| Путь | Что это |
|------|---------|
| `CLAUDE.md` | Тонкий хаб правил (авто-грузится каждую сессию): общение, Memory Bank, Git-регламент, speckit |
| `.claude/skills/` | Скиллы: `flow`, `status`, `publish`, `review-gate`, `ca-review`, `checkpoint`, `debt`, `deepthink`, `help`, `speckit.*` |
| `.claude/agents/` | 6 ролей ревью-каскада `flow-*` (router/finder/reviewer/advocate/expert/builder) |
| `.claude/settings.json` | Хук `SessionStart` (авто-подгрузка индекса банка) + statusline |
| `.claude/code-analysis/` | Пороги каскада (`scheduler-config.json`) + зоны эскалации (`architecture-zones.json` — заполнить) |
| `.specify/` | speckit: `feature.json`, `memory/constitution.md` (шаблон), generic-база `templates/` |
| `memory-bank/` | Скелет базы знаний (хабы + регламент); контент дописывается под проект |
| `scripts/` | `mb_recall.py` (recall-shortlist), `check_memory_links.py` (целостность `[[links]]`) |
| `install.sh` / `install.ps1` | Установка каркаса в целевой проект (skip-existing / `--force`) |

## Подключение в проект

**Новый проект** — клонируй и убери историю фреймворка:
```bash
git clone <repo-url> my-project && cd my-project && rm -rf .git && git init
```

**Существующий проект** — запусти инсталлер, указав его каталог (не перезаписывает существующие файлы):
```bash
./install.sh /path/to/target-project          # POSIX
```
```powershell
./install.ps1 -Target C:\path\to\target-project   # Windows
```
Добавь `--force` / `-Force`, чтобы перезаписать уже существующие файлы.

## После установки (обязательные шаги)

1. **Заполни `CLAUDE.md`** — блок «О проекте» (стек, запуск, тесты).
2. **Заполни `memory-bank/areas/architecture.md` и `constraints.md`** под свой проект.
3. **Допиши `.specify/memory/constitution.md`** — принципы проекта (или прогони `/speckit.constitution`).
4. **Заполни `.claude/code-analysis/architecture-zones.json`** — самые чувствительные модули
   (зоны эскалации ревью). Пустой список = зоны не заданы.
5. **Ветки:** каркас предполагает `develop` (рабочая интеграция) и `main` (релизы). Создай
   `develop`, если его нет: `git checkout -b develop`.
6. **Проверь банк:** `python3 scripts/check_memory_links.py` (stdlib, venv не нужен).

## Модель работы (кратко)

- **Memory Bank** — курируемое знание в `memory-bank/` (PARA: projects/areas/resources/archive),
  индекс `memory-bank/README.md` авто-грузится хуком. Правь на `develop`. Регламент —
  `memory-bank/areas/memory-regimen.md`.
- **Git-регламент** — авто-завершение задачи по триггеру «цель закрыта» (коммит → мерж
  `feat`→`develop` → пуш). Полностью в `CLAUDE.md`; точные команды — `memory-bank/resources/commands.md`.
- **speckit** — для нетривиальных фич: `specify → clarify → plan → tasks → analyze → implement`.
  Шаблоны — только из `memory-bank/resources/speckit-templates/`.
- **Команды** — оркестратор `/flow <цель>`, дашборд `/status`, справка `/help`.

> Скиллы/агенты написаны на русском (проект-конвенция общения). Если нужен другой язык
> взаимодействия — поправь правило «Общение» в `CLAUDE.md` и формулировки скиллов.
