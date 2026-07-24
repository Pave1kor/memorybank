# Каталог команд

_Что здесь: применяемые скиллы, служебные скрипты, точные Git-рецепты и канонические
последовательности «Дальше:». Это **единственное место** git-рецептов — `CLAUDE.md` и
`flow/SKILL.md` ссылаются сюда (`[[commands]]`), не копируют._

## Скиллы

Оркестрация и атомарные глаголы (вызов — `/<имя>`; полная справка — `/help`):

| Скилл | Роль |
|-------|------|
| `flow` | Оркестратор: диспетчер целей (фича/долг/идея), speckit-цикл, реализация, ревью, публикация |
| `status` | Read-only дашборд: ветка, активная фича, прогресс, долги/идеи |
| `publish` | Завершение цели: ревью-гейт → Memory Bank → коммит → мерж feat→develop → пуш |
| `review-gate` | Scope-aware выбор ревьюера (`/code-review` узкий · `/ca-review` широкий) + триаж |
| `ca-review` | Мультиагентный cost-aware каскад ревью диффа (flow-router→finder→reviewer→[advocate]→[expert]) |
| `checkpoint` | Контрольная точка контекста: session flush (durable в банк) + очистка эфемерного + уступка хода |
| `debt` | Запись долга/идеи в `roadmap.md` (стабильный якорь `[slug]`), работу НЕ запускает |
| `deepthink` | Глубокий последовательный разбор (нативный extended-thinking) |
| `help` | Справка по воркфлоу-командам |
| `speckit.specify` | Фаза speckit: `spec.md` по описанию задачи |
| `speckit.clarify` | Фаза speckit: устранить пробелы/неоднозначности |
| `speckit.plan` | Фаза speckit: `plan.md` с архитектурными решениями |
| `speckit.tasks` | Фаза speckit: `tasks.md` (чеклист) |
| `speckit.analyze` | Фаза speckit: кросс-сверка артефактов (ОБЯЗАТЕЛЕН) |
| `speckit.implement` | Фаза speckit: реализация по `tasks.md` |
| `speckit.constitution` | Правка конституции проекта + Sync Impact Report |
| `speckit.checklist` | Чек-лист качества требований |
| `speckit.taskstoissues` | Экспорт `tasks.md` в issue-трекер |

## Скрипты

| Скрипт | Назначение |
|--------|-----------|
| `scripts/mb_recall.py` | Shortlist top-k релевантных заметок (`query "<тема>"`), `rebuild` индекса, `atomize-signal` |
| `scripts/check_memory_links.py` | Целостность `[[links]]` + бюджет хабов + сверка каталога команд (stdlib) |

> Windows — `py scripts/…`; POSIX — `python3 scripts/…`.

## Git-рецепты

> **Единственное место** этих рецептов. КОГДА и ЧТО коммитить — политика в `CLAUDE.md`
> («Git-регламент»); здесь — точные команды.

- **Опубликовать новую ветку фичи** (сразу после создания):
  `git checkout -b feat/NNN-<slug> develop && git push -u origin feat/NNN-<slug>`
- **Синхронизация фиче-ветки с develop** (ПЕРЕД началом работы на существующей `feat/NNN-*`
  и всякий раз, когда `develop` уехал вперёд): `git fetch origin && git merge origin/develop
  && git push`. Обязательна: регламенты/агенты/банк (`.claude/*`, `memory-bank/`) живут на
  `develop` — несинхронизированная фича работает по УСТАРЕВШИМ правилам.
  Конфликт → `git merge --abort`, СТОП, спроси пользователя.
- **Разведка перед работой** (read-only): `git status -sb`, `git log --oneline -15`,
  `git diff --stat`, `git branch -vv`.
- **Коммит на текущей ветке + публикация** (после избирательного `git add <пути>`, НЕ `-A`
  вслепую): `git commit -m "<conventional msg>" && git push` — сообщение последней строкой
  `Co-Authored-By: <текущая модель сессии> <noreply@anthropic.com>` (точную подпись даёт
  харнесс; НЕ хардкодить модель). **Каждый коммит пушится** сразу — даже промежуточный на фиче-ветке.
- **Завершение `feat/NNN` → develop** (по триггеру публикации, тесты зелёные):
  `git checkout develop && git pull --ff-only && git merge feat/NNN-<slug> && git push origin develop`,
  затем **обязательно удалить слитую ветку** (локально + на `origin`):
  `git branch -d feat/NNN-<slug> && git push origin --delete feat/NNN-<slug>`.
  Конфликт мержа → `git merge --abort`, **СТОП**, спроси пользователя.
- **Уборка-по-мержу** (в ТОМ ЖЕ проходе, сразу после удаления ветки):
  1. **Worktree** слитой фичи: `git worktree list` → `git worktree remove <path>` → `git worktree prune`.
     Не удаляй чужие/незавершённые worktrees.
  2. **Устаревший код**, который фича ретайрила/замещала: удалённые модули, замещённые файлы,
     мёртвые импорты. Правило: заменила — старое удаляется в её же завершении. Сомнение (код
     точно мёртв?) — не удаляй наугад, вынеси развилкой.
- **Прямо на `develop`** (записи банка, roadmap):
  `git add <пути> && git commit -m "…" && git push origin develop`.

`main` — только по явной команде. Не форсь (`--force`), не скипай хуки (`--no-verify`) без
явной просьбы. Мерж `feat`→`develop` — только по триггеру «вся цель закрыта».

## Канонические последовательности

Ориентир для блока «**Дальше:**» — на каждом шаге понятно, какой скилл предложить следующим.

- **new-feature:** `speckit.specify → clarify → plan → tasks → analyze → implement →
  review-gate → publish`. На `analyze` развилка (CRITICAL/HIGH) чинится в артефактах.
- **work-goal:** `(найти цель через status/roadmap) → [speckit-цикл, ЕСЛИ нет spec.md и цель
  нетривиальна] → implement (пачками по tasks.md) → checkpoint (на границе пачки) →
  review-gate → publish`.
- **debt:** `debt <текст>` — терминальный шаг; следующий вызов — отдельный `flow <slug>`.

Терминал любой цепочки, если следующий шаг неочевиден — «цель закрыта / жди пользователя».
