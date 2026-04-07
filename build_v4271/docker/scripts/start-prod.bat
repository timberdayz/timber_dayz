@echo off
REM ===================================================
REM 西虹ERP系统 - 生产环境启动脚本（Windows）
REM ===================================================
REM 功能：构建并启动完整的生产环境
REM 使用方式：docker\scripts\start-prod.bat
REM ===================================================

chcp 65001 > nul
setlocal enabledelayedexpansion

cls
echo ==========================================
echo 西虹ERP系统 - 生产环境部署
echo ==========================================
echo.

REM 自动切换到项目根目录
if exist "..\..\docker-compose.yml" (
    cd ..\..
    echo [i] 已自动切换到项目根目录
    echo.
)

REM 检查是否在项目根目录
if not exist "docker-compose.yml" (
    echo [错误] 无法找到docker-compose.yml
    echo [i] 请确保在项目根目录执行此脚本
    echo.
    echo 当前目录: %CD%
    echo.
    pause
    exit /b 1
)

REM 检查Docker
echo [*] 检查环境...
docker --version > nul 2>&1
if errorlevel 1 (
    echo [错误] Docker未安装
    pause
    exit /b 1
)

docker-compose --version > nul 2>&1
if errorlevel 1 (
    echo [错误] Docker Compose未安装
    pause
    exit /b 1
)

REM 检查.env文件
if not exist ".env" (
    echo [错误] 未找到.env文件
    echo [i] 请复制env.production.example为.env并修改配置
    pause
    exit /b 1
)

echo [√] 环境检查通过
echo.

REM 备份数据
echo [*] 备份现有数据...
if exist "data" (
    for /f "delims=" %%i in ('dir /b /a "data" 2^>nul') do (
        set "has_data=1"
        goto :backup
    )
)
echo [i] 无需备份（数据目录为空）
goto :build

:backup
set backup_dir=backups\before_deploy_%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set backup_dir=%backup_dir: =0%
mkdir "%backup_dir%" 2>nul
xcopy /E /I /Q data "%backup_dir%\data" > nul
echo [√] 数据已备份到: %backup_dir%
echo.

:build
REM 构建镜像
echo [*] 构建Docker镜像...
echo [i] 这可能需要几分钟时间...
echo.

echo [*] 构建后端镜像...
docker build -f Dockerfile.backend -t xihong-erp-backend:latest .
if errorlevel 1 (
    echo [错误] 后端镜像构建失败
    pause
    exit /b 1
)

echo [*] 构建前端镜像...
docker build -f Dockerfile.frontend -t xihong-erp-frontend:latest .
if errorlevel 1 (
    echo [错误] 前端镜像构建失败
    pause
    exit /b 1
)

echo [√] 镜像构建完成
echo.

REM 启动服务
echo [*] 启动生产环境服务...
docker-compose --profile production up -d
if errorlevel 1 (
    echo [错误] 服务启动失败
    pause
    exit /b 1
)
echo [√] 服务启动完成
echo.

REM 健康检查 - PostgreSQL
echo [*] 执行健康检查...
echo [i] 等待PostgreSQL...
set /a count=0
:wait_postgres
set /a count+=1
if %count% gtr 60 (
    echo [错误] PostgreSQL启动超时
    pause
    exit /b 1
)
docker-compose exec -T postgres pg_isready -U erp_user -d xihong_erp > nul 2>&1
if errorlevel 1 (
    echo|set /p="."
    timeout /t 1 /nobreak > nul
    goto wait_postgres
)
echo.
echo [√] PostgreSQL健康
echo.

REM 健康检查 - 后端API
echo [i] 等待后端API...
set /a count=0
:wait_backend
set /a count+=1
if %count% gtr 60 (
    echo [错误] 后端API启动超时
    pause
    exit /b 1
)
curl -f http://localhost:8001/health > nul 2>&1
if errorlevel 1 (
    echo|set /p="."
    timeout /t 1 /nobreak > nul
    goto wait_backend
)
echo.
echo [√] 后端API健康
echo.

REM 健康检查 - 前端
echo [i] 等待前端服务...
set /a count=0
:wait_frontend
set /a count+=1
if %count% gtr 30 (
    echo [错误] 前端服务启动超时
    pause
    exit /b 1
)
curl -f http://localhost:5174 > nul 2>&1
if errorlevel 1 (
    echo|set /p="."
    timeout /t 1 /nobreak > nul
    goto wait_frontend
)
echo.
echo [√] 前端服务健康
echo.

echo [√] 所有服务健康检查通过
echo.

REM 显示部署信息
echo ==========================================
echo 🎉 西虹ERP系统 - 生产环境部署成功！
echo ==========================================
echo.
echo 📊 服务状态：
docker-compose ps
echo.
echo 🌐 访问地址：
echo   前端:        http://localhost:5174
echo   后端API:     http://localhost:8001
echo   API文档:     http://localhost:8001/api/docs
echo   健康检查:    http://localhost:8001/health
echo.
echo 📂 数据持久化：
echo   PostgreSQL数据: Docker卷 xihong_erp_postgres_data
echo   应用数据:       .\data
echo   日志文件:       .\logs
echo.
echo ⚙️  管理命令：
echo   查看日志:   docker-compose logs -f
echo   停止服务:   docker-compose down
echo   重启服务:   docker-compose restart
echo   查看状态:   docker-compose ps
echo.
echo ==========================================
echo.

pause

