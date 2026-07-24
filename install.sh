#!/usr/bin/env bash
# Устанавливает фреймворк Memory Bank (правила/скиллы/агенты/банк) в целевой проект.
#
#   ./install.sh /path/to/target-project [--force]
#
# По умолчанию НЕ перезаписывает уже существующие в целевом проекте файлы (skip-existing),
# чтобы не затереть локальные правки. --force перезаписывает.
#
# Что копируется: .claude/ .specify/ memory-bank/ scripts/ CLAUDE.md
# Что НЕ копируется: сам install.*, README.md фреймворка, .git/
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-}"
FORCE=0
[ "${2:-}" = "--force" ] && FORCE=1

if [ -z "$TARGET" ]; then
  echo "Usage: ./install.sh /path/to/target-project [--force]" >&2
  exit 1
fi
if [ ! -d "$TARGET" ]; then
  echo "!! Target directory does not exist: $TARGET" >&2
  exit 1
fi
if [ "$(cd "$TARGET" && pwd)" = "$SRC" ]; then
  echo "!! Target is the framework repo itself — choose another directory." >&2
  exit 1
fi

ITEMS=( ".claude" ".specify" "memory-bank" "scripts" "CLAUDE.md" )

# Эфемерное/мусор (gitignored в фреймворке) — НИКОГДА не переносим в целевой проект.
EXCLUDE_BASENAMES=( ".recall-index.json" "last-run-log.json" "import-graph.json" ".DS_Store" "Thumbs.db" )
is_excluded() {
  local b; b="$(basename "$1")"
  for e in "${EXCLUDE_BASENAMES[@]}"; do [ "$b" = "$e" ] && return 0; done
  case "$1" in *__pycache__*|*.pyc) return 0;; esac
  return 1
}

copied=0; skipped=0
copy_file() {
  local rel="$1" s="$SRC/$1" d="$TARGET/$1"
  if is_excluded "$rel"; then return; fi
  if [ -e "$d" ] && [ "$FORCE" -eq 0 ]; then
    echo "  skip (exists): $rel"; skipped=$((skipped+1)); return
  fi
  mkdir -p "$(dirname "$d")"
  cp "$s" "$d"
  echo "  copy: $rel"; copied=$((copied+1))
}

echo "Installing Memory Bank framework → $TARGET  (force=$FORCE)"
for item in "${ITEMS[@]}"; do
  if [ -f "$SRC/$item" ]; then
    copy_file "$item"
  elif [ -d "$SRC/$item" ]; then
    while IFS= read -r -d '' f; do
      rel="${f#"$SRC"/}"
      copy_file "$rel"
    done < <(find "$SRC/$item" -type f -print0)
  fi
done

echo
echo "Done. copied=$copied skipped=$skipped"
echo "Next steps in $TARGET:"
echo "  1) Заполни CLAUDE.md (блок «О проекте»), memory-bank/areas/{architecture,constraints}.md"
echo "  2) Допиши .specify/memory/constitution.md и .claude/code-analysis/architecture-zones.json"
echo "  3) Убедись, что ветки develop/main существуют (git checkout -b develop, если нужно)"
echo "  4) Проверь банк: python3 scripts/check_memory_links.py"
