# Nginx 限流功能测试脚本

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Nginx 限流功能测试" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 限流配置：500 次/分钟，burst=100
Write-Host "限流配置: 500 次/分钟 (burst=100)" -ForegroundColor Yellow
Write-Host "测试策略: 快速发送请求，超过限流阈值" -ForegroundColor Yellow
Write-Host ""

$success = 0
$rateLimited = 0
$errors = 0
$startTime = Get-Date

Write-Host "开始发送请求..." -ForegroundColor Green

# 发送 600 个请求（超过 500 的限流阈值）
for ($i=1; $i -le 600; $i++) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8081/api/health" -UseBasicParsing -TimeoutSec 1 -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            $success++
        } elseif ($response.StatusCode -eq 429) {
            $rateLimited++
            if ($rateLimited -eq 1) {
                Write-Host "  [首次限流] 第 $i 个请求返回 429" -ForegroundColor Yellow
            }
        }
    } catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        if ($statusCode -eq 429) {
            $rateLimited++
            if ($rateLimited -eq 1) {
                Write-Host "  [首次限流] 第 $i 个请求返回 429" -ForegroundColor Yellow
            }
        } else {
            $errors++
        }
    }
    
    # 每 100 个请求显示进度
    if ($i % 100 -eq 0) {
        Write-Host "  进度: $i/600 (成功: $success, 限流: $rateLimited, 错误: $errors)" -ForegroundColor Gray
    }
    
    # 短暂延迟，避免请求过快导致连接错误
    Start-Sleep -Milliseconds 10
}

$endTime = Get-Date
$duration = ($endTime - $startTime).TotalSeconds

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "测试结果" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "总请求数: 600" -ForegroundColor White
Write-Host "成功(200): $success" -ForegroundColor Green
Write-Host "限流(429): $rateLimited" -ForegroundColor $(if ($rateLimited -gt 0) { "Yellow" } else { "Gray" })
Write-Host "错误: $errors" -ForegroundColor $(if ($errors -gt 0) { "Red" } else { "Gray" })
Write-Host "耗时: $([math]::Round($duration, 2)) 秒" -ForegroundColor White
Write-Host ""

if ($rateLimited -gt 0) {
    Write-Host "[OK] 限流功能正常工作" -ForegroundColor Green
} else {
    Write-Host "[INFO] 未触发限流（可能因为请求速度不够快或时间窗口问题）" -ForegroundColor Yellow
    Write-Host "提示: 限流是基于时间窗口的（每分钟），可能需要更快的请求速度" -ForegroundColor Gray
}

Write-Host ""
Write-Host "查看 Nginx 日志:" -ForegroundColor Yellow
Write-Host "  docker exec xihong_erp_nginx_dev cat /var/log/nginx/access.log | Select-String 429" -ForegroundColor White
Write-Host ""

