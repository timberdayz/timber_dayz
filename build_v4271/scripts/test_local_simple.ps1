# 简化的本地测试脚本

Write-Host "`n[测试] 验证配置..." -ForegroundColor Yellow
docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile production config > $null 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] 配置验证通过" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] 配置验证失败" -ForegroundColor Red
    exit 1
}

Write-Host "`n[测试] 检查服务定义..." -ForegroundColor Yellow
$config = docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile production config 2>&1
$services = @("backend", "frontend", "nginx", "postgres", "redis", "celery-worker", "celery-beat")
$found = 0
foreach ($s in $services) {
    if ($config -match "  $s:") {
        Write-Host "  [OK] $s" -ForegroundColor Green
        $found++
    }
}
Write-Host "  找到: $found/$($services.Count) 个服务" -ForegroundColor Cyan

Write-Host "`n[测试] 当前运行的服务..." -ForegroundColor Yellow
docker ps --filter "name=xihong_erp" --format "table {{.Names}}\t{{.Status}}"

Write-Host "`n[测试] PostgreSQL 健康检查..." -ForegroundColor Yellow
docker exec xihong_erp_postgres pg_isready -U erp_user -d xihong_erp 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] PostgreSQL 健康" -ForegroundColor Green
}

Write-Host "`n[测试] Redis 健康检查..." -ForegroundColor Yellow
docker exec xihong_erp_redis redis-cli ping 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Redis 健康" -ForegroundColor Green
}

Write-Host "`n[完成] 基础服务测试完成" -ForegroundColor Green
Write-Host "`n[下一步] 如需启动所有服务，运行:" -ForegroundColor Yellow
Write-Host "  docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile production up -d" -ForegroundColor Cyan
