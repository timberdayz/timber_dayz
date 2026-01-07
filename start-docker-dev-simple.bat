@echo off
REM ===================================================
REM 西虹ERP - 开发环境快速启动
REM ===================================================

chcp 65001 > nul
setlocal enabledelayedexpansion

REM 自动切换到项目根目录
if exist "..\..\docker-compose.yml" (
    cd ..\..
)

cls
echo ==========================================
echo 西虹ERP系统 - 开发环境启动
echo ==========================================
echo.

REM 检查docker-compose.yml
if not exist "docker-compose.yml" (
    echo [ERROR] Cannot find docker-compose.yml
    echo [INFO] Current dir: %CD%
    pause
    exit /b 1
)

REM 检查Docker
docker --version > nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker not installed
    pause
    exit /b 1
)

docker info > nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker not running
    echo [INFO] Please start Docker Desktop
    pause
    exit /b 1
)

echo [OK] Docker is ready
echo.

REM 创建目录
if not exist "data" mkdir data
if not exist "temp" mkdir temp
if not exist "logs" mkdir logs
if not exist "downloads" mkdir downloads
if not exist "backups" mkdir backups

REM 启动服务
echo [INFO] Starting services...
docker-compose --profile dev up -d
if errorlevel 1 (
    echo [ERROR] Failed to start services
    echo.
    echo Common issues:
    echo - Docker image pull timeout: Run fix-docker-mirror.bat
    echo - Port already in use: Change port in .env file
    pause
    exit /b 1
)

echo [OK] Services started
echo.

REM 等待数据库
echo [INFO] Waiting for PostgreSQL...
set /a count=0
:wait_db
set /a count+=1
if %count% gtr 30 (
    echo [ERROR] PostgreSQL timeout
    pause
    exit /b 1
)
docker-compose exec -T postgres pg_isready -U erp_user -d xihong_erp > nul 2>&1
if errorlevel 1 (
    echo|set /p="."
    timeout /t 1 /nobreak > nul
    goto wait_db
)
echo.
echo [OK] PostgreSQL is ready
echo.

REM 初始化数据库
echo [INFO] Checking database...
docker-compose exec -T postgres psql -U erp_user -d xihong_erp -c "\dt" | findstr "accounts" > nul 2>&1
if errorlevel 1 (
    echo [INFO] Initializing database tables...
    python docker\postgres\init-tables.py
    echo.
)

REM 显示信息
echo ==========================================
echo SUCCESS! Development environment is ready
echo ==========================================
echo.
echo Service URLs:
echo   PostgreSQL:  localhost:5432
echo   pgAdmin:     http://localhost:5051
echo.
echo Database Connection:
echo   Database: xihong_erp_dev
echo   Username: erp_dev
echo   Password: dev_pass_2025
echo.
echo pgAdmin Login:
echo   Email:    dev@xihong.com
echo   Password: dev123
echo.
echo Next Steps:
echo   1. Start backend:  cd backend ^&^& uvicorn main:app --reload
echo   2. Start frontend: cd frontend ^&^& npm run dev
echo   3. Open browser:   http://localhost:5173
echo.
echo Commands:
echo   View logs: docker-compose logs -f postgres
echo   Stop:      docker-compose down
echo   Restart:   docker-compose restart postgres
echo.
echo ==========================================
echo.

pause

