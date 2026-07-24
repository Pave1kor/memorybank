# Speckit-шаблоны (курированные, источник истины)

Шаблоны артефактов speckit-цикла живут в `memory-bank/resources/speckit-templates/`.
**Speckit читает шаблоны ТОЛЬКО отсюда**, а не из `.specify/templates/` (те — исходный
generic-набор Spec Kit, оставлен как база/референс).

## Состав

| Артефакт фичи | Шаблон | Кто создаёт |
|---------------|--------|-------------|
| `spec.md`  | `speckit-templates/spec.md`  | `specify` |
| `plan.md`  | `speckit-templates/plan.md`  | `plan` |
| `tasks.md` | `speckit-templates/tasks.md` | `tasks` |
| `checklists/requirements.md` | `speckit-templates/checklist.md` | `specify` (Quality Validation) и `/speckit.checklist` |
| `research.md` | `speckit-templates/research.md` | `plan`, Phase 0 |
| `data-model.md` | `speckit-templates/data-model.md` | `plan`, Phase 1 |
| `contracts/<тема>.md` | `speckit-templates/contract.md` | `plan`, Phase 1 (пропустить, если фича без внешних интерфейсов) |
| `quickstart.md` | `speckit-templates/quickstart.md` | `plan`, Phase 1 |

Шаблоны **домен-нейтральны** — с плейсхолдерами `[...]`. Заполняй под стек своего проекта.
Если проект вырастает и появляется устойчивое разделение (напр. фронт/бэк) — можно завести
специализированные варианты (`spec-backend.md`/`spec-frontend.md` и т.д.), но начинай с единых.

## Как применять в speckit-цикле

1. `specify` — скопируй `spec.md` в `specs/NNN-<slug>/spec.md`, замени плейсхолдеры `[...]`;
   чек-лист качества — из `checklist.md`.
2. `plan` — скопируй `plan.md` (заполни Technical Context/Constitution Check под свой стек и
   конституцию); Phase 0/1 артефакты — из `research.md`/`data-model.md`/`contract.md`/`quickstart.md`.
3. `tasks` — скопируй `tasks.md` (фазы по user story, пути под свой проект).
4. `analyze` — ОБЯЗАТЕЛЕН: кросс-сверка spec↔plan↔tasks↔конституция, находки применить к артефактам.

Полный регламент цикла — [[workflow]]; инварианты — [[constraints]]; архитектура/пути — [[architecture]].

## Рабочие правила, вшитые в шаблоны

- **Read-before-Edit/Write.** Перед правкой (Edit) ИЛИ перезаписью существующего файла (Write)
  его НУЖНО сначала прочитать (Read), иначе инструмент падает.
- **Бюджет заметок.** Держи шаблоны компактными; кросс-ссылки внутри шаблонов давай в
  backticks/фенсах, чтобы линк-чекер не считал их за `[[links]]`.
