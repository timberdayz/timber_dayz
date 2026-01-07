# Nginx 开发环境测试脚本
# 用途：测试 Nginx 开发环境部署

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Nginx 开发环境测试" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查前置条件
Write-Host "[1/5] 检查前置条件..." -ForegroundColor Yellow

# 检查后端服务
Write-Host "  检查后端服务 (http://localhost:8001)..." -ForegroundColor Gray
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8001/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
    Write-Host "  [OK] 后端服务正在运行" -ForegroundColor Green
    $backendRunning = $true
} catch {
    Write-Host "  [WARN] 后端服务未运行，请先启动后端服务" -ForegroundColor Yellow
    Write-Host "    启动命令: cd backend; uvicorn main:app --reload --host 0.0.0.0 --port 8001" -ForegroundColor Gray
    $backendRunning = $false
}

# 检查前端服务
Write-Host "  检查前端服务 (http://localhost:5173)..." -ForegroundColor Gray
try {
    $response = Invoke-WebRequest -Uri "http://localhost:5173" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
    Write-Host "  [OK] 前端服务正在运行" -ForegroundColor Green
    $frontendRunning = $true
} catch {
    Write-Host "  [WARN] 前端服务未运行，请先启动前端服务" -ForegroundColor Yellow
    Write-Host "    启动命令: cd frontend; npm run dev" -ForegroundColor Gray
    $frontendRunning = $false
}

if (-not $backendRunning -or -not $frontendRunning) {
    Write-Host ""
    Write-Host "[提示] 虽然服务未运行，但可以继续测试 Nginx 配置" -ForegroundColor Yellow
    Write-Host ""
}

# 启动 Nginx
Write-Host "[2/5] 启动 Nginx 服务..." -ForegroundColor Yellow
docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev-nginx up -d
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Nginx 服务已启动" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] Nginx 服务启动失败" -ForegroundColor Red
    exit 1
}

# 等待 Nginx 启动
Write-Host "  等待 Nginx 启动..." -ForegroundColor Gray
Start-Sleep -Seconds 3

# 检查 Nginx 状态
Write-Host "[3/5] 检查 Nginx 服务状态..." -ForegroundColor Yellow
$nginxStatus = docker-compose -f docker-compose.yml -f docker-compose.dev.yml ps nginx
Write-Host $nginxStatus

# 测试健康检查
Write-Host "[4/5] 测试 Nginx 健康检查..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8080/health" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
    Write-Host "  [OK] Nginx 健康检查通过 (状态码: $($response.StatusCode))" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] Nginx 健康检查失败: $_" -ForegroundColor Yellow
    Write-Host "  查看日志: docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs nginx" -ForegroundColor Gray
}

# 测试反向代理
Write-Host "[5/5] 测试反向代理功能..." -ForegroundColor Yellow

if ($backendRunning) {
    Write-Host "  测试后端 API 代理..." -ForegroundColor Gray
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8080/api/health" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        Write-Host "  [OK] 后端 API 代理正常 (状态码: $($response.StatusCode))" -ForegroundColor Green
    } catch {
        Write-Host "  [WARN] 后端 API 代理失败: $_" -ForegroundColor Yellow
    }
} else {
    Write-Host "  [SKIP] 后端服务未运行，跳过后端 API 代理测试" -ForegroundColor Gray
}

if ($frontendRunning) {
    Write-Host "  测试前端代理..." -ForegroundColor Gray
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8080/" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        Write-Host "  [OK] 前端代理正常 (状态码: $($response.StatusCode))" -ForegroundColor Green
    } catch {
        Write-Host "  [WARN] 前端代理失败: $_" -ForegroundColor Yellow
    }
} else {
    Write-Host "  [SKIP] 前端服务未运行，跳过前端代理测试" -ForegroundColor Gray
}

# 显示测试结果
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "测试完成" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "访问地址:" -ForegroundColor Yellow
Write-Host "  - Nginx: http://localhost:8080" -ForegroundColor White
Write-Host "  - 后端 API: http://localhost:8080/api/health" -ForegroundColor White
Write-Host "  - 前端: http://localhost:8080/" -ForegroundColor White
Write-Host ""
Write-Host "查看日志:" -ForegroundColor Yellow
Write-Host "  docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f nginx" -ForegroundColor White
Write-Host ""
Write-Host "停止 Nginx:" -ForegroundColor Yellow
Write-Host "  docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev-nginx down" -ForegroundColor White
Write-Host ""


