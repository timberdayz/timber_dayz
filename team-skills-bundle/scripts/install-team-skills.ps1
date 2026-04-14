param(
  [string]$TargetDir = "",
  [switch]$Force
)

$ErrorActionPreference = "Stop"

$bundleRoot = Split-Path -Parent $PSScriptRoot
$skillNames = @(
  "sea-metrics-language",
  "sea-business-review",
  "sea-product-selection",
  "sea-funnel-action-playbook"
)

if ([string]::IsNullOrWhiteSpace($TargetDir)) {
  if ($env:CODEX_HOME) {
    $TargetDir = Join-Path $env:CODEX_HOME "skills"
  } else {
    $TargetDir = Join-Path $HOME ".codex\\skills"
  }
}

New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null

foreach ($skill in $skillNames) {
  $source = Join-Path $bundleRoot $skill
  $dest = Join-Path $TargetDir $skill

  if ((Test-Path $dest) -and -not $Force) {
    Write-Host "[SKIP] $skill already exists at $dest (use -Force to overwrite)"
    continue
  }

  if (Test-Path $dest) {
    Remove-Item -Recurse -Force $dest
  }

  Copy-Item -Recurse -Force $source $dest
  Write-Host "[OK] Installed $skill -> $dest"
}

Write-Host ""
Write-Host "Install complete."
Write-Host "Target: $TargetDir"
