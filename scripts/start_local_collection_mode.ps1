param(
    [switch]$SkipChecks
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

$env:XIHONG_ENV_PROFILE = "collection"

if (-not $SkipChecks) {
    & python "$repoRoot\scripts\check_local_run_env.py" --profile collection
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

& python "$repoRoot\run.py" --local
exit $LASTEXITCODE
