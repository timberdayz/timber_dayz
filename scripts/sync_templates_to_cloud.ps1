# 模板数据云端同步脚本（方案A：压缩传输优化）
# 适用于国内外网络环境，通过压缩减少传输时间

param(
    [string]$SSH_KEY = "C:\Users\18689\.ssh\github_actions_deploy",
    [string]$SSH_USER = "deploy",
    [string]$SSH_HOST = "134.175.222.171",
    [string]$LOCAL_DB_HOST = "localhost",
    [int]$LOCAL_DB_PORT = 15432,
    [string]$LOCAL_DB_USER = "erp_user",
    [string]$LOCAL_DB_PASSWORD = "erp_pass_2025",
    [string]$LOCAL_DB_NAME = "xihong_erp",
    [string]$CLOUD_DB_USER = "erp_user",
    [string]$CLOUD_DB_NAME = "xihong_erp",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# 项目根目录
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$TempDir = Join-Path $ProjectRoot "temp"
if (-not (Test-Path $TempDir)) {
    New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
}

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$SqlFile = Join-Path $TempDir "templates_export_$Timestamp.sql"
$GzFile = "$SqlFile.gz"
$RemoteFile = "/tmp/templates_export_$Timestamp.sql.gz"

Write-Host ""
Write-Host ("=" * 80) -ForegroundColor Cyan
Write-Host "模板数据云端同步脚本（方案A：压缩传输优化）" -ForegroundColor Cyan
Write-Host ("=" * 80) -ForegroundColor Cyan
Write-Host ""
Write-Host "[优化特性]" -ForegroundColor Yellow
Write-Host "  - 使用gzip压缩减少传输时间（通常减少70-90%）" -ForegroundColor Gray
Write-Host "  - SSH压缩传输加速" -ForegroundColor Gray
Write-Host "  - 适用于国内外网络环境" -ForegroundColor Gray
Write-Host ""

if ($DryRun) {
    Write-Host "[模式] DRY-RUN（模拟模式，只导出不上传）" -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "配置信息:" -ForegroundColor Cyan
Write-Host "  本地数据库: ${LOCAL_DB_HOST}:${LOCAL_DB_PORT}/${LOCAL_DB_NAME}" -ForegroundColor Gray
Write-Host "  云端服务器: ${SSH_USER}@${SSH_HOST}" -ForegroundColor Gray
Write-Host "  云端数据库: postgres:5432/${CLOUD_DB_NAME}" -ForegroundColor Gray
Write-Host ""

# 查找 pg_dump 可执行文件
$pgDumpPath = $null
if (Get-Command pg_dump -ErrorAction SilentlyContinue) {
    $pgDumpPath = "pg_dump"
} else {
    # 尝试在常见位置查找
    $possiblePaths = @(
        "C:\Program Files\PostgreSQL\*\bin\pg_dump.exe",
        "C:\Program Files (x86)\PostgreSQL\*\bin\pg_dump.exe"
    )
    foreach ($path in $possiblePaths) {
        $found = Get-ChildItem -Path $path -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) {
            $pgDumpPath = $found.FullName
            break
        }
    }
}

if (-not $pgDumpPath) {
    Write-Host "[FAIL] 未找到 pg_dump，请确保PostgreSQL客户端工具已安装并在PATH中" -ForegroundColor Red
    exit 1
}

# 步骤1：导出本地模板数据
Write-Host "[步骤1] 导出本地模板数据..." -ForegroundColor Cyan
try {
    $env:PGPASSWORD = $LOCAL_DB_PASSWORD
    $pgDumpArgs = @(
        "-h", $LOCAL_DB_HOST,
        "-p", $LOCAL_DB_PORT.ToString(),
        "-U", $LOCAL_DB_USER,
        "-d", $LOCAL_DB_NAME,
        "-t", "field_mapping_templates",
        "--data-only",
        "--column-inserts",
        "-f", $SqlFile
    )
    
    $pgDumpProcess = Start-Process -FilePath $pgDumpPath -ArgumentList $pgDumpArgs -Wait -PassThru -NoNewWindow
    
    if ($pgDumpProcess.ExitCode -ne 0) {
        throw "pg_dump 执行失败，退出码: $($pgDumpProcess.ExitCode)"
    }
    
    if (-not (Test-Path $SqlFile)) {
        throw "导出文件未生成: $SqlFile"
    }
    
    $sqlSize = (Get-Item $SqlFile).Length
    Write-Host "[OK] 模板数据已导出: $SqlFile ($([math]::Round($sqlSize/1KB, 2)) KB)" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] 导出失败: $_" -ForegroundColor Red
    exit 1
}

# 步骤2：压缩SQL文件
Write-Host ""
Write-Host "[步骤2] 压缩导出文件..." -ForegroundColor Cyan
try {
    # 使用 .NET GZipStream 进行压缩（PowerShell原生支持）
    $inputFile = [System.IO.File]::OpenRead($SqlFile)
    $outputFile = [System.IO.File]::Create($GzFile)
    $gzipStream = New-Object System.IO.Compression.GZipStream($outputFile, [System.IO.Compression.CompressionMode]::Compress)
    
    $inputFile.CopyTo($gzipStream)
    $gzipStream.Close()
    $outputFile.Close()
    $inputFile.Close()
    
    $gzSize = (Get-Item $GzFile).Length
    $compressionRatio = [math]::Round((1 - $gzSize / $sqlSize) * 100, 1)
    Write-Host "[OK] 文件已压缩: $GzFile ($([math]::Round($gzSize/1KB, 2)) KB, 压缩率: ${compressionRatio}%)" -ForegroundColor Green
    
    # 删除未压缩的SQL文件
    Remove-Item $SqlFile -Force
    Write-Host "[INFO] 已删除未压缩文件" -ForegroundColor Gray
} catch {
    Write-Host "[FAIL] 压缩失败: $_" -ForegroundColor Red
    exit 1
}

if ($DryRun) {
    Write-Host ""
    Write-Host "[DRY-RUN] 模拟模式，跳过上传和导入步骤" -ForegroundColor Yellow
    Write-Host "[INFO] 压缩文件位置: $GzFile" -ForegroundColor Gray
    exit 0
}

# 步骤3：上传到云端服务器
Write-Host ""
Write-Host "[步骤3] 上传文件到云端服务器..." -ForegroundColor Cyan
if (Test-Path $GzFile) {
    $gzSize = (Get-Item $GzFile).Length
    Write-Host "[INFO] 文件大小: $([math]::Round($gzSize/1KB, 2)) KB" -ForegroundColor Gray
} else {
    Write-Host "[FAIL] 压缩文件不存在: $GzFile" -ForegroundColor Red
    exit 1
}
try {
    $scpArgs = @(
        "-i", $SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ServerAliveInterval=30",
        "-o", "Compression=yes",
        $GzFile,
        "${SSH_USER}@${SSH_HOST}:${RemoteFile}"
    )
    
    $scpProcess = Start-Process -FilePath "scp" -ArgumentList $scpArgs -Wait -PassThru -NoNewWindow
    
    if ($scpProcess.ExitCode -ne 0) {
        throw "scp 上传失败，退出码: $($scpProcess.ExitCode)"
    }
    
    Write-Host "[OK] 文件已上传到云端: ${RemoteFile}" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] 上传失败: $_" -ForegroundColor Red
    exit 1
}

# 步骤4：在云端服务器导入模板数据
Write-Host ""
Write-Host "[步骤4] 在云端服务器导入模板数据..." -ForegroundColor Cyan
try {
    $importCmd = "cd /opt/xihong_erp && gunzip -c ${RemoteFile} | docker exec -i xihong_erp_postgres psql -U ${CLOUD_DB_USER} -d ${CLOUD_DB_NAME}"
    
    $sshArgs = @(
        "-i", $SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ServerAliveInterval=30",
        "-o", "Compression=yes",
        "${SSH_USER}@${SSH_HOST}",
        $importCmd
    )
    
    $sshProcess = Start-Process -FilePath "ssh" -ArgumentList $sshArgs -Wait -PassThru -NoNewWindow -RedirectStandardOutput "$TempDir\import_output.txt" -RedirectStandardError "$TempDir\import_error.txt"
    
    if ($sshProcess.ExitCode -ne 0) {
        $errorContent = Get-Content "$TempDir\import_error.txt" -Raw -ErrorAction SilentlyContinue
        Write-Host "[FAIL] 导入失败: $errorContent" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "[OK] 模板数据已导入到云端数据库" -ForegroundColor Green
    
    # 显示导入输出（最后几行）
    if (Test-Path "$TempDir\import_output.txt") {
        $output = Get-Content "$TempDir\import_output.txt" -Tail 5 -ErrorAction SilentlyContinue
        if ($output) {
            Write-Host "[INFO] 导入输出:" -ForegroundColor Gray
            $output | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
        }
    }
} catch {
    Write-Host "[FAIL] 导入过程出错: $_" -ForegroundColor Red
    exit 1
}

# 步骤5：验证云端模板数量
Write-Host ""
Write-Host "[步骤5] 验证云端模板数量..." -ForegroundColor Cyan
try {
    $verifyCmd = "docker exec xihong_erp_postgres psql -U ${CLOUD_DB_USER} -d ${CLOUD_DB_NAME} -t -c `"SELECT COUNT(*) as total, COUNT(*) FILTER (WHERE status='published') as published FROM field_mapping_templates;`""
    
    $sshArgs = @(
        "-i", $SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "Compression=yes",
        "${SSH_USER}@${SSH_HOST}",
        $verifyCmd
    )
    
    $verifyOutput = & ssh $sshArgs 2>&1
    $verifyExitCode = $LASTEXITCODE
    
    if ($verifyExitCode -eq 0) {
        $verifyOutput = $verifyOutput.Trim()
        if ($verifyOutput -match '\s+(\d+)\s+\|\s+(\d+)') {
            $total = $matches[1]
            $published = $matches[2]
            Write-Host "[OK] 云端模板统计:" -ForegroundColor Green
            Write-Host "  总数: $total" -ForegroundColor Gray
            Write-Host "  已发布: $published" -ForegroundColor Gray
        } else {
            Write-Host "[OK] 云端模板: $verifyOutput" -ForegroundColor Green
        }
    } else {
        Write-Host "[WARN] 验证失败: $verifyOutput" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[WARN] 验证过程出错: $_" -ForegroundColor Yellow
}

# 清理临时文件
Write-Host ""
Write-Host "[清理] 清理临时文件..." -ForegroundColor Cyan
try {
    if (Test-Path $GzFile) {
        Remove-Item $GzFile -Force
        Write-Host "[OK] 已清理本地临时文件: $GzFile" -ForegroundColor Green
    }
    
    # 清理云端临时文件
    $cleanupCmd = "rm -f ${RemoteFile}"
    $sshArgs = @(
        "-i", $SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "${SSH_USER}@${SSH_HOST}",
        $cleanupCmd
    )
    Start-Process -FilePath "ssh" -ArgumentList $sshArgs -Wait -NoNewWindow | Out-Null
    Write-Host "[OK] 已清理云端临时文件: ${RemoteFile}" -ForegroundColor Green
} catch {
    Write-Host "[WARN] 清理临时文件时出错: $_" -ForegroundColor Yellow
}

# 清理导入输出文件
if (Test-Path "$TempDir\import_output.txt") {
    Remove-Item "$TempDir\import_output.txt" -Force -ErrorAction SilentlyContinue
}
if (Test-Path "$TempDir\import_error.txt") {
    Remove-Item "$TempDir\import_error.txt" -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host ("=" * 80) -ForegroundColor Green
Write-Host "同步完成！" -ForegroundColor Green
Write-Host ("=" * 80) -ForegroundColor Green
Write-Host ""
