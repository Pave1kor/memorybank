<#
.SYNOPSIS
  Устанавливает фреймворк Memory Bank (правила/скиллы/агенты/банк) в целевой проект.
.EXAMPLE
  ./install.ps1 -Target C:\path\to\target-project
  ./install.ps1 -Target C:\path\to\target-project -Force
.DESCRIPTION
  По умолчанию НЕ перезаписывает уже существующие в целевом проекте файлы (skip-existing).
  -Force перезаписывает. Копирует: .claude/ .specify/ memory-bank/ scripts/ CLAUDE.md
  НЕ копирует: install.*, README.md фреймворка, .git/
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)] [string] $Target,
  [switch] $Force
)
$ErrorActionPreference = 'Stop'

$Src = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not (Test-Path -LiteralPath $Target -PathType Container)) {
  Write-Error "Target directory does not exist: $Target"; exit 1
}
$TargetFull = (Resolve-Path -LiteralPath $Target).Path
if ($TargetFull -eq $Src) {
  Write-Error "Target is the framework repo itself — choose another directory."; exit 1
}

$Items = @('.claude', '.specify', 'memory-bank', 'scripts', 'CLAUDE.md')
$copied = 0; $skipped = 0

function Copy-One([string]$Rel) {
  $s = Join-Path $Src $Rel
  $d = Join-Path $TargetFull $Rel
  if ((Test-Path -LiteralPath $d) -and -not $Force) {
    Write-Host "  skip (exists): $Rel"; $script:skipped++; return
  }
  $dir = Split-Path -Parent $d
  if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  Copy-Item -LiteralPath $s -Destination $d -Force
  Write-Host "  copy: $Rel"; $script:copied++
}

Write-Host "Installing Memory Bank framework -> $TargetFull  (force=$($Force.IsPresent))"
foreach ($item in $Items) {
  $sp = Join-Path $Src $item
  if (Test-Path -LiteralPath $sp -PathType Leaf) {
    Copy-One $item
  } elseif (Test-Path -LiteralPath $sp -PathType Container) {
    Get-ChildItem -LiteralPath $sp -Recurse -File | ForEach-Object {
      $rel = $_.FullName.Substring($Src.Length + 1)
      Copy-One $rel
    }
  }
}

Write-Host ""
Write-Host "Done. copied=$copied skipped=$skipped"
Write-Host "Next steps in $TargetFull :"
Write-Host "  1) Заполни CLAUDE.md (блок 'О проекте'), memory-bank/areas/{architecture,constraints}.md"
Write-Host "  2) Допиши .specify/memory/constitution.md и .claude/code-analysis/architecture-zones.json"
Write-Host "  3) Убедись, что ветки develop/main существуют"
Write-Host "  4) Проверь банк: py scripts/check_memory_links.py"
