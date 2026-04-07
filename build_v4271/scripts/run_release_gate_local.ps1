# Local release gate checks (same as CI, except DB migration test needs Docker)
# Usage: .\scripts\run_release_gate_local.ps1
# With changed files: .\scripts\run_release_gate_local.ps1 -ChangedFilesList "temp\changed_files.txt"

param([string]$ChangedFilesList = "")

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location $projectRoot
$failed = $false

Write-Host ""
Write-Host "========== Verify Critical Tables Foreign Keys ==========" -ForegroundColor Cyan
python scripts/test_migration_foreign_keys.py
if ($LASTEXITCODE -ne 0) { $failed = $true; Write-Host "[FAIL]" -ForegroundColor Red } else { Write-Host "[PASS]" -ForegroundColor Green }

Write-Host ""
Write-Host "========== Validate API Contracts ==========" -ForegroundColor Cyan
if ($ChangedFilesList -and (Test-Path $ChangedFilesList)) {
    python scripts/validate_api_contracts.py --changed-files $ChangedFilesList
} else {
    python scripts/validate_api_contracts.py
}
if ($LASTEXITCODE -ne 0) { $failed = $true; Write-Host "[FAIL]" -ForegroundColor Red } else { Write-Host "[PASS]" -ForegroundColor Green }

Write-Host ""
Write-Host "========== Validate Frontend API Methods ==========" -ForegroundColor Cyan
if ($ChangedFilesList -and (Test-Path $ChangedFilesList)) {
    python scripts/validate_frontend_api_methods.py --changed-files $ChangedFilesList
} else {
    python scripts/validate_frontend_api_methods.py
}
if ($LASTEXITCODE -ne 0) { $failed = $true; Write-Host "[FAIL]" -ForegroundColor Red } else { Write-Host "[PASS]" -ForegroundColor Green }

Write-Host ""
Write-Host "========== Validate Database Fields ==========" -ForegroundColor Cyan
python scripts/validate_database_fields.py
if ($LASTEXITCODE -ne 0) { $failed = $true; Write-Host "[FAIL]" -ForegroundColor Red } else { Write-Host "[PASS]" -ForegroundColor Green }

Write-Host ""
if ($failed) {
    Write-Host "========== Release gate: FAILED ==========" -ForegroundColor Red
    exit 1
}
Write-Host "========== Release gate: ALL PASSED ==========" -ForegroundColor Green
Write-Host "Note: DB migration test (PostgreSQL) is run in CI only."
exit 0
