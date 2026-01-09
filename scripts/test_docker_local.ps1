# 本地 Docker 测试脚本
# 测试修复后的 Docker Compose 配置

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "本地 Docker 测试" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# 1. 验证配置
Write-Host "[1/5] 验证 Docker Compose 配置..." -ForegroundColor Yellow
docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile production config > $null 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] 配置验证通过" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] 配置验证失败" -ForegroundColor Red
    docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile production config 2>&1 | Select-Object -Last 10
    exit 1
}

# 2. 检查服务定义
Write-Host "`n[2/5] 检查服务定义..." -ForegroundColor Yellow
$services = @("backend", "frontend", "nginx", "postgres", "redis", "celery-worker", "celery-beat")
$config_output = docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile production config 2>&1

foreach ($service in $services) {
    if ($config_output -match "  $service:") {
        Write-Host "  [OK] $service 服务已定义" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] $service 服务未找到" -ForegroundColor Yellow
    }
}

# 3. 清理旧容器（可选）
Write-Host "`n[3/5] 清理旧容器..." -ForegroundColor Yellow
$clean = Read-Host "  是否清理旧容器? (y/n)"
if ($clean -eq "y" -or $clean -eq "Y") {
    docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile production down -v 2>$null
    Write-Host "  [OK] 旧容器已清理" -ForegroundColor Green
} else {
    Write-Host "  [SKIP] 跳过清理" -ForegroundColor Yellow
}

# 4. 启动基础服务（仅 postgres 和 redis）
Write-Host "`n[4/5] 启动基础服务（postgres, redis）..." -ForegroundColor Yellow
docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile production up -d postgres redis

if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] 基础服务启动命令执行成功" -ForegroundColor Green
    Write-Host "  [等待] 等待服务启动（15秒）..." -ForegroundColor Cyan
    Start-Sleep -Seconds 15
    
    # 检查服务状态
    Write-Host "`n  服务状态:" -ForegroundColor Cyan
    docker-compose -f docker-compose.yml -f docker-compose.prod.yml ps postgres redis
} else {
    Write-Host "  [FAIL] 基础服务启动失败" -ForegroundColor Red
    exit 1
}

# 5. 健康检查
Write-Host "`n[5/5] 健康检查..." -ForegroundColor Yellow

# PostgreSQL 健康检查
$pg_health = docker exec xihong_erp_postgres pg_isready -U erp_user -d xihong_erp 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] PostgreSQL 健康检查通过" -ForegroundColor Green
} else {
    Write-Host "  [WARN] PostgreSQL 健康检查失败" -ForegroundColor Yellow
}

# Redis 健康检查
$redis_health = docker exec xihong_erp_redis redis-cli ping 2>$null
if ($redis_health -eq "PONG") {
    Write-Host "  [OK] Redis 健康检查通过" -ForegroundColor Green
} else {
    Write-Host "  [WARN] Redis 健康检查失败" -ForegroundColor Yellow
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "测试完成！" -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "[下一步]" -ForegroundColor Yellow
Write-Host "  如果基础服务正常，可以启动所有服务:" -ForegroundColor White
Write-Host "    docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile production up -d" -ForegroundColor Cyan
Write-Host "`n  查看所有服务状态:" -ForegroundColor White
Write-Host "    docker-compose -f docker-compose.yml -f docker-compose.prod.yml ps" -ForegroundColor Cyan
Write-Host "`n  查看服务日志:" -ForegroundColor White
Write-Host "    docker-compose -f docker-compose.yml -f docker-compose.prod.yml logs -f" -ForegroundColor Cyan
