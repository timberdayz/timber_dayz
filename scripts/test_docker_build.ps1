# =====================================================
# Docker 镜像构建测试脚本 (PowerShell)
# =====================================================
# 用于本地测试 Docker 镜像构建，验证 Dockerfile 是否正确
# =====================================================

$ErrorActionPreference = "Stop"

function Print-Message {
    param([string]$Message)
    Write-Host "[测试] $Message" -ForegroundColor Green
}

function Print-Error {
    param([string]$Message)
    Write-Host "[错误] $Message" -ForegroundColor Red
}

function Print-Info {
    param([string]$Message)
    Write-Host "[信息] $Message" -ForegroundColor Blue
}

# 项目根目录
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Print-Message "开始 Docker 镜像构建测试"
Write-Host ""

# 检查 Docker 是否运行
try {
    docker info | Out-Null
} catch {
    Print-Error "Docker 未运行，请启动 Docker"
    exit 1
}

# 测试后端镜像构建
Print-Message "测试后端镜像构建..."
$backendLog = Join-Path $env:TEMP "docker_build_backend.log"
try {
    docker build -f Dockerfile.backend -t xihong_erp_backend:test `
        --build-arg PYTHON_VERSION=3.11 `
        . 2>&1 | Tee-Object -FilePath $backendLog | Out-Null
    
    if ($LASTEXITCODE -eq 0) {
        Print-Message "后端镜像构建成功"
        docker images | Select-String "xihong_erp_backend:test"
    } else {
        throw "构建失败"
    }
} catch {
    Print-Error "后端镜像构建失败"
    Print-Info "查看构建日志: $backendLog"
    if (Test-Path $backendLog) {
        Get-Content $backendLog -Tail 20
    }
    exit 1
}

Write-Host ""

# 测试前端镜像构建
Print-Message "测试前端镜像构建..."
$frontendLog = Join-Path $env:TEMP "docker_build_frontend.log"
try {
    docker build -f Dockerfile.frontend -t xihong_erp_frontend:test `
        --target production `
        --build-arg NODE_VERSION=18 `
        --build-arg VITE_API_URL=http://localhost:8001 `
        . 2>&1 | Tee-Object -FilePath $frontendLog | Out-Null
    
    if ($LASTEXITCODE -eq 0) {
        Print-Message "前端镜像构建成功"
        docker images | Select-String "xihong_erp_frontend:test"
    } else {
        throw "构建失败"
    }
} catch {
    Print-Error "前端镜像构建失败"
    Print-Info "查看构建日志: $frontendLog"
    if (Test-Path $frontendLog) {
        Get-Content $frontendLog -Tail 20
    }
    exit 1
}

Write-Host ""
Print-Message "所有镜像构建测试通过！"
Print-Info "清理测试镜像:"
Print-Info "  docker rmi xihong_erp_backend:test xihong_erp_frontend:test"

