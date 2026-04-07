# 测试Schema初始化脚本 (PowerShell版本)
# 用于验证docker/postgres/init.sql中的Schema创建是否正确

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Schema初始化脚本测试" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

$ErrorActionPreference = "Stop"
$allTestsPassed = $true

# 测试1: 检查init.sql文件是否存在
Write-Host "[TEST 1] 检查init.sql文件是否存在..." -ForegroundColor Yellow
if (Test-Path "docker/postgres/init.sql") {
    Write-Host "[OK] init.sql文件存在" -ForegroundColor Green
} else {
    Write-Host "[FAIL] init.sql文件不存在" -ForegroundColor Red
    exit 1
}

# 测试2: 检查Schema创建语句是否存在
Write-Host "[TEST 2] 检查Schema创建语句..." -ForegroundColor Yellow
$content = Get-Content "docker/postgres/init.sql" -Raw
$schemaCount = ([regex]::Matches($content, "CREATE SCHEMA IF NOT EXISTS")).Count
if ($schemaCount -ge 5) {
    Write-Host "[OK] 找到 $schemaCount 个Schema创建语句" -ForegroundColor Green
} else {
    Write-Host "[FAIL] 只找到 $schemaCount 个Schema创建语句（预期至少5个）" -ForegroundColor Red
    $allTestsPassed = $false
}

# 测试3: 检查必需的Schema是否存在
Write-Host "[TEST 3] 检查必需的Schema..." -ForegroundColor Yellow
$requiredSchemas = @("a_class", "b_class", "c_class", "core", "finance")
foreach ($schema in $requiredSchemas) {
    if ($content -match "CREATE SCHEMA IF NOT EXISTS $schema") {
        Write-Host "[OK] Schema '$schema' 创建语句存在" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] Schema '$schema' 创建语句不存在" -ForegroundColor Red
        $allTestsPassed = $false
    }
}

# 测试4: 检查搜索路径设置是否存在
Write-Host "[TEST 4] 检查搜索路径设置..." -ForegroundColor Yellow
if ($content -match "ALTER DATABASE.*SET search_path") {
    Write-Host "[OK] 数据库级别搜索路径设置存在" -ForegroundColor Green
} else {
    Write-Host "[FAIL] 数据库级别搜索路径设置不存在" -ForegroundColor Red
    $allTestsPassed = $false
}

if ($content -match "ALTER ROLE erp_user SET search_path") {
    Write-Host "[OK] erp_user搜索路径设置存在" -ForegroundColor Green
} else {
    Write-Host "[FAIL] erp_user搜索路径设置不存在" -ForegroundColor Red
    $allTestsPassed = $false
}

# 测试5: 检查SQL语法（基本检查）
Write-Host "[TEST 5] 检查SQL语法（基本检查）..." -ForegroundColor Yellow
if ($content -match "CREATE SCHEMA IF NOT EXISTS" -and 
    $content -match "ALTER DATABASE" -and 
    $content -match "ALTER ROLE") {
    Write-Host "[OK] SQL语法基本检查通过" -ForegroundColor Green
} else {
    Write-Host "[FAIL] SQL语法基本检查失败" -ForegroundColor Red
    $allTestsPassed = $false
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
if ($allTestsPassed) {
    Write-Host "所有测试通过！" -ForegroundColor Green
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "下一步：" -ForegroundColor Yellow
    Write-Host "1. 提交代码到Git"
    Write-Host "2. 在全新数据库环境中测试部署"
    Write-Host "3. 验证Schema是否正确创建"
    Write-Host ""
    exit 0
} else {
    Write-Host "部分测试失败！" -ForegroundColor Red
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host ""
    exit 1
}
