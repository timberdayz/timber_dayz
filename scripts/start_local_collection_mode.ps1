param(
    [switch]$SkipChecks
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

$env:XIHONG_ENV_PROFILE = "collection"

try {
    docker stop xihong_erp_backend_api xihong_erp_backend_collector | Out-Null
} catch {
    Write-Host "[INFO] skip docker backend stop: $($_.Exception.Message)"
}

if (-not $SkipChecks) {
    & python "$repoRoot\scripts\check_local_run_env.py" --profile collection
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

& python "$repoRoot\run.py" --local
exit $LASTEXITCODE
