# 生产环境 Docker 部署测试脚本
# 模拟云端部署场景，验证所有服务是否正常工作

param(
    [switch]$FullTest,
    [switch]$SkipStartup
)

$ErrorActionPreference = "Continue"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "生产环境 Docker 部署测试" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

$results = @{}

# 1. 配置验证
Write-Host "[1/9] 配置验证..." -ForegroundColor Yellow
docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.metabase.yml --profile production config > $null 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] 配置验证通过" -ForegroundColor Green
    $results["配置验证"] = $true
} else {
    Write-Host "  [FAIL] 配置验证失败" -ForegroundColor Red
    $results["配置验证"] = $false
    exit 1
}

# 2. 服务启动（如果未跳过）
if (-not $SkipStartup) {
    Write-Host "`n[2/9] 服务启动..." -ForegroundColor Yellow
    Write-Host "  清理旧容器..." -ForegroundColor Gray
    docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.metabase.yml --profile production down 2>$null
    
    Write-Host "  启动核心服务（包含 Metabase）..." -ForegroundColor Gray
    docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.metabase.yml --profile production up -d 2>&1 | Out-Null
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] 服务启动命令执行成功" -ForegroundColor Green
        Write-Host "  等待服务启动（30秒）..." -ForegroundColor Gray
        Start-Sleep -Seconds 30
        $results["服务启动"] = $true
    } else {
        Write-Host "  [FAIL] 服务启动失败" -ForegroundColor Red
        $results["服务启动"] = $false
        exit 1
    }
} else {
    Write-Host "`n[2/9] 服务启动 (跳过)" -ForegroundColor Yellow
    $results["服务启动"] = $true
}

# 3. 容器状态检查
Write-Host "`n[3/9] 容器状态检查..." -ForegroundColor Yellow
$containers = docker ps --filter "name=xihong_erp" --format "{{.Names}}" 2>&1
$expected = @("xihong_erp_postgres", "xihong_erp_redis", "xihong_erp_backend", 
              "xihong_erp_frontend", "xihong_erp_nginx", "xihong_erp_celery_worker", 
              "xihong_erp_celery_beat", "xihong_erp_celery_exporter", "xihong_erp_metabase")
$found = 0
foreach ($exp in $expected) {
    if ($containers -match $exp) {
        Write-Host "  [OK] $exp" -ForegroundColor Green
        $found++
    } else {
        Write-Host "  [FAIL] $exp 未运行" -ForegroundColor Red
    }
}
Write-Host "  运行中的容器: $found/$($expected.Count)" -ForegroundColor Cyan
$results["容器状态"] = ($found -eq $expected.Count)

# 4. PostgreSQL 健康检查
Write-Host "`n[4/9] PostgreSQL 健康检查..." -ForegroundColor Yellow
$pgHealth = docker exec xihong_erp_postgres pg_isready -U erp_user -d xihong_erp 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] PostgreSQL 健康" -ForegroundColor Green
    $results["PostgreSQL"] = $true
} else {
    Write-Host "  [FAIL] PostgreSQL 健康检查失败" -ForegroundColor Red
    $results["PostgreSQL"] = $false
}

# 5. Redis 健康检查
Write-Host "`n[5/9] Redis 健康检查..." -ForegroundColor Yellow
$redisHealth = docker exec xihong_erp_redis redis-cli ping 2>&1
if ($redisHealth -match "PONG") {
    Write-Host "  [OK] Redis 健康" -ForegroundColor Green
    $results["Redis"] = $true
} else {
    # 尝试带密码
    $redisHealth = docker exec xihong_erp_redis redis-cli -a redis_pass_2025 ping 2>&1
    if ($redisHealth -match "PONG") {
        Write-Host "  [OK] Redis 健康（使用密码）" -ForegroundColor Green
        $results["Redis"] = $true
    } else {
        Write-Host "  [WARN] Redis 健康检查失败" -ForegroundColor Yellow
        $results["Redis"] = $false
    }
}

# 6. 后端 API 健康检查
Write-Host "`n[6/9] 后端 API 健康检查..." -ForegroundColor Yellow
$maxRetries = 30
$backendOk = $false
for ($i = 0; $i -lt $maxRetries; $i++) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            Write-Host "  [OK] 后端 API 健康（尝试 $($i+1)/$maxRetries）" -ForegroundColor Green
            $backendOk = $true
            break
        }
    } catch {
        if ($i -lt $maxRetries - 1) {
            Start-Sleep -Seconds 2
        }
    }
}
if (-not $backendOk) {
    Write-Host "  [FAIL] 后端 API 健康检查超时" -ForegroundColor Red
}
$results["后端API"] = $backendOk

# 7. 前端健康检查
Write-Host "`n[7/9] 前端健康检查..." -ForegroundColor Yellow
$maxRetries = 20
$frontendOk = $false
for ($i = 0; $i -lt $maxRetries; $i++) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:3000" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            Write-Host "  [OK] 前端健康（尝试 $($i+1)/$maxRetries）" -ForegroundColor Green
            $frontendOk = $true
            break
        }
    } catch {
        if ($i -lt $maxRetries - 1) {
            Start-Sleep -Seconds 2
        }
    }
}
if (-not $frontendOk) {
    Write-Host "  [WARN] 前端健康检查超时（可能仍在启动）" -ForegroundColor Yellow
}
$results["前端"] = $frontendOk

# 8. Nginx 健康检查
Write-Host "`n[8/9] Nginx 健康检查..." -ForegroundColor Yellow
$maxRetries = 15
$nginxOk = $false
for ($i = 0; $i -lt $maxRetries; $i++) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            Write-Host "  [OK] Nginx 可访问（尝试 $($i+1)/$maxRetries）" -ForegroundColor Green
            $nginxOk = $true
            break
        }
    } catch {
        if ($i -lt $maxRetries - 1) {
            Start-Sleep -Seconds 2
        }
    }
}
if (-not $nginxOk) {
    Write-Host "  [WARN] Nginx 健康检查超时" -ForegroundColor Yellow
}
$results["Nginx"] = $nginxOk

# 9. Metabase 健康检查
Write-Host "`n[9/9] Metabase 健康检查..." -ForegroundColor Yellow
$maxRetries = 30
$metabaseOk = $false
for ($i = 0; $i -lt $maxRetries; $i++) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8080/api/health" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            Write-Host "  [OK] Metabase 健康（尝试 $($i+1)/$maxRetries）" -ForegroundColor Green
            $metabaseOk = $true
            break
        }
    } catch {
        if ($i -lt $maxRetries - 1) {
            Start-Sleep -Seconds 3  # Metabase 启动较慢
        }
    }
}
if (-not $metabaseOk) {
    Write-Host "  [WARN] Metabase 健康检查超时（可能仍在启动，首次启动需要1-2分钟）" -ForegroundColor Yellow
}
$results["Metabase"] = $metabaseOk

# 生成报告
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "测试报告" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$total = $results.Count
$passed = ($results.Values | Where-Object { $_ -eq $true }).Count

Write-Host "`n总测试数: $total" -ForegroundColor White
Write-Host "通过: $passed" -ForegroundColor Green
Write-Host "失败: $($total - $passed)" -ForegroundColor $(if (($total - $passed) -gt 0) { "Red" } else { "Green" })
Write-Host "通过率: $([math]::Round($passed/$total*100, 1))%" -ForegroundColor Cyan

Write-Host "`n详细结果:" -ForegroundColor White
foreach ($key in $results.Keys) {
    $status = if ($results[$key]) { "[OK]" } else { "[FAIL]" }
    $color = if ($results[$key]) { "Green" } else { "Red" }
    Write-Host "  $status $key" -ForegroundColor $color
}

Write-Host "`n========================================" -ForegroundColor Cyan

# 显示服务状态
Write-Host "`n当前服务状态:" -ForegroundColor Yellow
docker ps --filter "name=xihong_erp" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

if ($passed -eq $total) {
    Write-Host "`n[成功] 所有测试通过！可以部署到云端。" -ForegroundColor Green
    exit 0
} else {
    Write-Host "`n[警告] 部分测试失败，请检查失败项后再部署。" -ForegroundColor Yellow
    exit 1
}
