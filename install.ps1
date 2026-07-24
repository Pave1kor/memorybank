<#
.SYNOPSIS
  Installs the Memory Bank framework (rules/skills/agents/bank) into a target project.
.EXAMPLE
  ./install.ps1 -Target C:\path\to\target-project
  ./install.ps1 -Target C:\path\to\target-project -Force
.DESCRIPTION
  By default does NOT overwrite files that already exist in the target (skip-existing).
  -Force overwrites. Copies: .claude/ .specify/ memory-bank/ scripts/ CLAUDE.md
  Does NOT copy: install.*, the framework README.md, .git/
  NOTE: kept ASCII-only on purpose so Windows PowerShell 5.1 parses it regardless of console codepage.
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
  Write-Error "Target is the framework repo itself - choose another directory."; exit 1
}

$Items = @('.claude', '.specify', 'memory-bank', 'scripts', 'CLAUDE.md')
# Ephemeral/junk (gitignored in the framework) - never carried into a target project.
$ExcludeNames = @('.recall-index.json', 'last-run-log.json', 'import-graph.json', '.DS_Store', 'Thumbs.db')
$script:copied = 0
$script:skipped = 0

function Copy-One([string]$Rel) {
  $leaf = Split-Path -Leaf $Rel
  if (($ExcludeNames -contains $leaf) -or ($Rel -like '*__pycache__*') -or ($Rel -like '*.pyc')) { return }
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
Write-Host "Done. copied=$($script:copied) skipped=$($script:skipped)"
Write-Host "Next steps in the target project:"
Write-Host "  1) Fill in CLAUDE.md ('About the project' block), memory-bank/areas/{architecture,constraints}.md"
Write-Host "  2) Complete .specify/memory/constitution.md and .claude/code-analysis/architecture-zones.json"
Write-Host "  3) Make sure develop/main branches exist (git checkout -b develop)"
Write-Host "  4) Verify the bank: py scripts/check_memory_links.py"
