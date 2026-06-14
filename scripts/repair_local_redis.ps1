param(
    [switch]$FixAof,
    [switch]$Rebuild
)

$ErrorActionPreference = "Stop"

if (($FixAof -and $Rebuild) -or (-not $FixAof -and -not $Rebuild)) {
    Write-Host "[ERROR] Pass exactly one of -FixAof or -Rebuild." -ForegroundColor Red
    exit 1
}

$composeArgs = @("-f", "docker-compose.yml", "-f", "docker-compose.dev.yml")
$redisVolume = "xihong_erp_redis_data"
$servicesToStop = @("redis", "celery-worker", "celery-beat")

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Local Redis recovery tool" -ForegroundColor Cyan
Write-Host "For local dev volume only: $redisVolume" -ForegroundColor Yellow
Write-Host "Do not use this script for production Redis." -ForegroundColor Red
Write-Host "============================================================" -ForegroundColor Cyan

Write-Host "[Step] Stopping local Redis and Celery containers..." -ForegroundColor Yellow
docker compose @composeArgs stop @servicesToStop | Out-Null

if ($FixAof) {
    Write-Host "[Step] Attempting Redis AOF repair..." -ForegroundColor Yellow
    docker run --rm -v "${redisVolume}:/data" redis:7-alpine sh -c "cd /data/appendonlydir && cp appendonly.aof.manifest appendonly.aof.manifest.bak && cp appendonly.aof.6.incr.aof appendonly.aof.6.incr.aof.bak && printf 'y\n' | redis-check-aof --fix appendonly.aof.manifest"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] AOF repair failed. Inspect the volume or retry with -Rebuild." -ForegroundColor Red
        exit $LASTEXITCODE
    }

    Write-Host "[Step] Starting local Redis and Celery containers..." -ForegroundColor Yellow
    docker compose @composeArgs --profile dev --profile dev-full up -d @servicesToStop | Out-Null
    Write-Host "[OK] AOF repair command completed. Re-run python run.py --local to verify." -ForegroundColor Green
    exit 0
}

if ($Rebuild) {
    $confirmation = Read-Host "This will delete local Redis volume '$redisVolume' and clear local queue/cache data. Type REBUILD to continue"
    if ($confirmation -ne "REBUILD") {
        Write-Host "[INFO] Rebuild cancelled." -ForegroundColor Yellow
        exit 1
    }

    Write-Host "[Step] Removing local Redis volume..." -ForegroundColor Yellow
    docker volume rm $redisVolume
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to remove local Redis volume." -ForegroundColor Red
        exit $LASTEXITCODE
    }

    Write-Host "[Step] Starting local Redis and Celery containers..." -ForegroundColor Yellow
    docker compose @composeArgs --profile dev --profile dev-full up -d @servicesToStop | Out-Null
    Write-Host "[OK] Local Redis volume rebuilt. Re-run python run.py --local to verify." -ForegroundColor Green
    exit 0
}
