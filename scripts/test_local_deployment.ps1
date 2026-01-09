# 本地部署测试脚本
# 测试修复后的 Docker Compose 配置

param(
    [switch]$FullTest,
    [switch]$SkipBuild
)

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "本地 Docker 部署测试" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

$ErrorActionPreference = "Continue"

# 1. 验证配置
Write-Host "[1/7] 验证 Docker Compose 配置..." -ForegroundColor Yellow
$configCheck = docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile production config 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] 配置验证通过" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] 配置验证失败" -ForegroundColor Red
    $configCheck | Select-Object -Last 10
    exit 1
}

# 2. 检查服务定义
Write-Host "`n[2/7] 检查服务定义..." -ForegroundColor Yellow
$services = @("backend", "frontend", "nginx", "postgres", "redis", "celery-worker", "celery-beat")
$foundServices = 0

foreach ($service in $services) {
    if ($configCheck -match "  $service:") {
        Write-Host "  [OK] $service 服务已定义" -ForegroundColor Green
        $foundServices++
    } else {
        Write-Host "  [WARN] $service 服务未找到" -ForegroundColor Yellow
    }
}

Write-Host "`n  找到服务: $foundServices/$($services.Count)" -ForegroundColor Cyan

# 3. 检查必要的目录和文件
Write-Host "`n[3/7] 检查必要的目录和文件..." -ForegroundColor Yellow
$requiredPaths = @(
    "sql\init",
    "sql\init\01-init.sql"
)

foreach ($path in $requiredPaths) {
    if (Test-Path $path) {
        Write-Host "  [OK] $path 存在" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] $path 不存在" -ForegroundColor Yellow
        if ($path -like "*\01-init.sql") {
            $dir = Split-Path $path -Parent
            if (-not (Test-Path $dir)) {
                New-Item -ItemType Directory -Path $dir -Force | Out-Null
            }
            Set-Content -Path $path -Value "-- PostgreSQL 初始化脚本`nSET client_encoding = 'UTF8';"
            Write-Host "    [创建] $path" -ForegroundColor Green
        }
    }
}

# 4. 清理旧容器
Write-Host "`n[4/7] 清理旧容器..." -ForegroundColor Yellow
docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile production down 2>$null
Write-Host "  [OK] 清理完成" -ForegroundColor Green

# 5. 启动基础服务
Write-Host "`n[5/7] 启动基础服务（postgres, redis）..." -ForegroundColor Yellow
$startResult = docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile production up -d postgres redis 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] 基础服务启动命令执行成功" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] 基础服务启动失败" -ForegroundColor Red
    $startResult | Select-Object -Last 10
    exit 1
}

# 等待服务启动
Write-Host "  [等待] 等待服务启动（15秒）..." -ForegroundColor Cyan
Start-Sleep -Seconds 15

# 6. 检查服务状态
Write-Host "`n[6/7] 检查服务状态..." -ForegroundColor Yellow
docker ps --filter "name=xihong_erp" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# 7. 健康检查
Write-Host "`n[7/7] 健康检查..." -ForegroundColor Yellow

# PostgreSQL 健康检查
Write-Host "  PostgreSQL..." -ForegroundColor Cyan
$pgHealth = docker exec xihong_erp_postgres pg_isready -U erp_user -d xihong_erp 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "    [OK] PostgreSQL 健康检查通过" -ForegroundColor Green
} else {
    Write-Host "    [WARN] PostgreSQL 健康检查失败" -ForegroundColor Yellow
    Write-Host "    输出: $pgHealth" -ForegroundColor Gray
}

# Redis 健康检查
Write-Host "  Redis..." -ForegroundColor Cyan
$redisHealth = docker exec xihong_erp_redis redis-cli ping 2>&1
if ($redisHealth -eq "PONG") {
    Write-Host "    [OK] Redis 健康检查通过" -ForegroundColor Green
} else {
    Write-Host "    [WARN] Redis 健康检查失败（可能需要密码）" -ForegroundColor Yellow
    Write-Host "    输出: $redisHealth" -ForegroundColor Gray
}

# 总结
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "测试完成！" -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Cyan

if ($FullTest) {
    Write-Host "[下一步] 启动所有服务..." -ForegroundColor Yellow
    Write-Host "  docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile production up -d" -ForegroundColor Cyan
} else {
    Write-Host "[下一步]" -ForegroundColor Yellow
    Write-Host "  如果基础服务正常，可以启动所有服务:" -ForegroundColor White
    Write-Host "    docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile production up -d" -ForegroundColor Cyan
    Write-Host "`n  查看所有服务状态:" -ForegroundColor White
    Write-Host "    docker-compose -f docker-compose.yml -f docker-compose.prod.yml ps" -ForegroundColor Cyan
}

Write-Host "`n========================================" -ForegroundColor Cyan
