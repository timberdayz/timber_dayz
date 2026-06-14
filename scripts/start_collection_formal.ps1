param(
    [switch]$SkipChecks
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

$env:XIHONG_ENV_PROFILE = "collection"

Write-Host "[Mode] Formal collection laptop mode: local headed backend, Docker infrastructure only"
Write-Host "[Guard] Docker backend-api/backend-collector will be stopped before startup"

try {
    docker stop xihong_erp_backend_api xihong_erp_backend_collector | Out-Null
} catch {
    Write-Host "[INFO] skip docker backend stop: $($_.Exception.Message)"
}

if (-not $SkipChecks) {
    & python "$repoRoot\scripts\check_local_run_env.py" --profile collection --require-cloud-tunnel
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[FAIL] Formal collection preflight failed. Confirm the SSH tunnel is running and CLOUD_SYNC_TUNNEL_HOST:CLOUD_SYNC_TUNNEL_PORT is reachable."
        exit $LASTEXITCODE
    }
}

& python "$repoRoot\run.py" --local
exit $LASTEXITCODE
