# Nginx 限流功能极端测试脚本
# 使用并发请求测试限流功能

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Nginx 限流功能极端测试（并发请求）" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "限流配置: 500 次/分钟 (burst=100)" -ForegroundColor Yellow
Write-Host "测试策略: 并发发送大量请求，快速超过限流阈值" -ForegroundColor Yellow
Write-Host ""

$concurrent = 50  # 并发数
$totalRequests = 600  # 总请求数

Write-Host "开始并发测试..." -ForegroundColor Green
Write-Host "并发数: $concurrent" -ForegroundColor White
Write-Host "总请求数: $totalRequests" -ForegroundColor White
Write-Host ""

$results = @()
$startTime = Get-Date

# 创建并发任务
$jobs = @()
for ($i = 1; $i -le $totalRequests; $i++) {
    $job = Start-Job -ScriptBlock {
        param($url, $requestId)
        try {
            $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            return @{
                Id = $requestId
                StatusCode = $response.StatusCode
                Success = $true
            }
        } catch {
            $statusCode = $_.Exception.Response.StatusCode.value__
            return @{
                Id = $requestId
                StatusCode = $statusCode
                Success = $false
            }
        }
    } -ArgumentList "http://localhost:8081/api/health", $i
    
    $jobs += $job
    
    # 每达到并发数，等待一批完成
    if ($jobs.Count -ge $concurrent) {
        $completed = $jobs | Wait-Job -Any
        $results += $completed | Receive-Job
        $completed | Remove-Job
        $jobs = $jobs | Where-Object { $_.State -eq 'Running' }
    }
}

# 等待所有任务完成
Write-Host "等待所有请求完成..." -ForegroundColor Gray
$remaining = $jobs | Wait-Job
$results += $remaining | Receive-Job
$remaining | Remove-Job

$endTime = Get-Date
$duration = ($endTime - $startTime).TotalSeconds

# 统计结果
$success = ($results | Where-Object { $_.StatusCode -eq 200 }).Count
$rateLimited = ($results | Where-Object { $_.StatusCode -eq 429 }).Count
$errors = ($results | Where-Object { $_.StatusCode -ne 200 -and $_.StatusCode -ne 429 }).Count
$otherStatus = $results | Where-Object { $_.StatusCode -ne 200 -and $_.StatusCode -ne 429 -and $_.StatusCode -ne $null } | Group-Object StatusCode | Select-Object Name, Count

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "测试结果" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "总请求数: $totalRequests" -ForegroundColor White
Write-Host "成功(200): $success" -ForegroundColor Green
Write-Host "限流(429): $rateLimited" -ForegroundColor $(if ($rateLimited -gt 0) { "Yellow" } else { "Gray" })
Write-Host "错误: $errors" -ForegroundColor $(if ($errors -gt 0) { "Red" } else { "Gray" })
Write-Host "耗时: $([math]::Round($duration, 2)) 秒" -ForegroundColor White
Write-Host "平均 QPS: $([math]::Round($totalRequests / $duration, 2))" -ForegroundColor White
Write-Host ""

if ($otherStatus) {
    Write-Host "其他状态码:" -ForegroundColor Yellow
    $otherStatus | ForEach-Object {
        Write-Host "  $($_.Name): $($_.Count)" -ForegroundColor Gray
    }
    Write-Host ""
}

if ($rateLimited -gt 0) {
    Write-Host "[OK] 限流功能正常工作！" -ForegroundColor Green
    Write-Host "触发限流的请求数: $rateLimited" -ForegroundColor Yellow
} else {
    Write-Host "[INFO] 未触发限流" -ForegroundColor Yellow
    Write-Host "可能原因:" -ForegroundColor Gray
    Write-Host "  1. 请求速度不够快（限流是基于时间窗口的）" -ForegroundColor Gray
    Write-Host "  2. burst 参数允许突发请求" -ForegroundColor Gray
    Write-Host "  3. 并发请求可能被分散到不同的时间窗口" -ForegroundColor Gray
}

Write-Host ""
Write-Host "查看 Nginx 限流日志:" -ForegroundColor Yellow
Write-Host "  docker exec xihong_erp_nginx_dev cat /var/log/nginx/access.log | Select-String 429" -ForegroundColor White
Write-Host ""



