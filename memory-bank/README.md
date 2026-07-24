# Memory Bank

Курируемая база знаний проекта. Организована по **PARA** (Projects/Areas/Resources/Archive)
+ Zettelkasten `[[links]]` между заметками. Грузи **только нужную** заметку под задачу — не всё подряд.

> Источник истины по коду — сам код и `CLAUDE.md`. Здесь — выжимки, решения и контекст,
> которые не выводятся напрямую из кода/гита. Обновляется по завершении задач.

## Карта файлов

| Категория | Файл | Когда читать |
|-----------|------|--------------|
| **Projects** | [projects/active-context.md](projects/active-context.md) | Что делаем сейчас: ветка, активная фича, планируемые, незакрытое |
| **Projects** | [projects/planned/](projects/planned/) | Детали планируемых фич — файл на фичу (`NNN-slug.md`); грузить ТОЛЬКО работая над ней |
| **Projects** | [projects/roadmap.md](projects/roadmap.md) | Тонкий ИНДЕКС открытых долгов/идей |
| **Projects** | [projects/ideas/](projects/ideas/), [projects/debts/](projects/debts/) | «Толстые» идеи/долги — файл на сущность; грузить по `[[ссылке]]` |
| **Areas** | [areas/architecture.md](areas/architecture.md) | Слои, потоки данных, дерево каталогов, ключевые модули |
| **Areas** | [areas/constraints.md](areas/constraints.md) | Инварианты и ограничения, которые нельзя нарушать |
| **Areas** | [areas/workflow.md](areas/workflow.md) | speckit-цикл, экономия контекста, recall-маршрутизация |
| **Areas** | [areas/memory-regimen.md](areas/memory-regimen.md) | Полный регламент банка (хабы/спицы, файл-на-фичу, атомизация) — при обновлении банка |
| **Resources** | [resources/decisions.md](resources/decisions.md) | Принятые архитектурные решения и их «почему» |
| **Resources** | [resources/commands.md](resources/commands.md) | Каталог скиллов/скриптов/git-рецептов + канонические последовательности |
| **Resources** | [resources/speckit-templates.md](resources/speckit-templates.md) | Шаблоны speckit (spec/plan/tasks/…) — читать только отсюда |
| **Archive** | [archive/index.md](archive/index.md) | Датированный индекс закрытых фич (файл-на-фичу в `archive/`) |

## Zettelkasten-ссылки

Заметки ссылаются через `[[name]]` (basename файла без `.md`) или `[[name#anchor]]`. Целостность
проверяет `python3 scripts/check_memory_links.py` (stdlib, venv не нужен) — резолвит `[[name]]` по
уникальному basename под `memory-bank/`, печатает нерезолвленные/неоднозначные, exit 0 при чистом.

## Регламент обновления

Полные правила (модель «хабы vs спицы», файл-на-фичу для planned/, атомизация долгов,
архивирование-по-закрытию, «только на `develop`») — **[[memory-regimen]]**. Кратко: правь на
`develop`; хабы (этот README, `active-context`, `roadmap`, `CLAUDE.md`) держи тонкими и под
бюджетом; детали — в спицах по требованию; прогоняй `check_memory_links.py` при обновлении.
