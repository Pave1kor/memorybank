#!/usr/bin/env node
// StatusLine для Claude Code: датчик БЮДЖЕТА КОНТЕКСТА оркестратора.
//
// Читает JSON со stdin (schema statusLine Claude Code) и печатает одну строку:
//   модель | каталог | ctx <N>k (<pct>%) [маркер]
//
// Поле context_window (CC v2.1.132+) даёт total_input_tokens / used_percentage /
// context_window_size. Пороги-маркеры согласованы с бюджет-триггером /checkpoint
// (.claude/skills/checkpoint/SKILL.md):
//   <80k  = ok      (рабочий потолок)
//   >=80k = ~cap    (норма на исходе)
//   >=120k= ! soft  (пора checkpoint на границе пачки)
//   >=160k= !! HARD (сброс немедленно)
//
// Node — единый лаунчер на всех ОС (на Windows `python` = заглушка, а `py`/`python3`
// расходятся между ОС; `node` одинаков везде и уже есть в проекте через frontend).
// Только stdin -> stdout, ничего не мутирует. Маркеры ASCII.
'use strict';
const fs = require('fs');

let data;
try {
  data = JSON.parse(fs.readFileSync(0, 'utf8'));
} catch (e) {
  process.exit(0);
}

const parts = [];

const model = data.model && data.model.display_name;
if (model) parts.push(String(model));

const ws = data.workspace || {};
const cur = ws.current_dir || data.cwd;
if (cur) {
  const base = String(cur).replace(/[\\/]+$/, '').split(/[\\/]/).pop();
  if (base) parts.push(base);
}

const cw = data.context_window || {};
const tokens = cw.total_input_tokens;
const pct = cw.used_percentage;
if (typeof tokens === 'number') {
  let mark;
  if (tokens >= 160000) mark = '!! HARD';
  else if (tokens >= 120000) mark = '! soft';
  else if (tokens >= 80000) mark = '~cap';
  else mark = 'ok';
  let seg = 'ctx ' + Math.round(tokens / 1000) + 'k';
  if (typeof pct === 'number') seg += ' (' + Math.round(pct) + '%)';
  seg += ' [' + mark + ']';
  parts.push(seg);
}

if (parts.length) process.stdout.write(parts.join(' | '));
