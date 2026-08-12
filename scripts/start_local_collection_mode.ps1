$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

$env:XIHONG_ENV_PROFILE = "development"

Write-Host "[Mode] Local development: local backend and frontend, Docker infrastructure only"
Write-Host "[Guard] Docker backend-api/backend-collector will be stopped before startup"

try {
    docker stop xihong_erp_backend_api xihong_erp_backend_collector | Out-Null
} catch {
    Write-Host "[INFO] skip docker backend stop: $($_.Exception.Message)"
}

& python "$repoRoot\run.py" --local
exit $LASTEXITCODE
