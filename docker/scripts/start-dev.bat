@echo off
REM ===================================================
REM 西虹ERP系统 - 开发环境启动脚本（Windows）
REM ===================================================
REM 功能：启动PostgreSQL和pgAdmin，供本地开发使用
REM 使用方式：docker\scripts\start-dev.bat
REM ===================================================

chcp 65001 > nul
setlocal enabledelayedexpansion

echo ==========================================
echo 西虹ERP系统 - 开发环境启动
echo ==========================================
echo.

REM 自动切换到项目根目录
REM 如果当前目录是 scripts，则切换到上两级目录
if exist "..\..\docker-compose.yml" (
    cd ..\..
    echo [i] 已自动切换到项目根目录
    echo.
)

REM 检查是否在项目根目录
if not exist "docker-compose.yml" (
    echo [错误] 无法找到docker-compose.yml
    echo [i] 请确保在项目根目录执行此脚本，或从项目根目录运行
    echo.
    echo 当前目录: %CD%
    echo.
    pause
    exit /b 1
)

REM 检查Docker是否安装
docker --version > nul 2>&1
if errorlevel 1 (
    echo [错误] Docker未安装，请先安装Docker Desktop
    pause
    exit /b 1
)

docker-compose --version > nul 2>&1
if errorlevel 1 (
    echo [错误] Docker Compose未安装
    pause
    exit /b 1
)

echo [√] Docker环境检查通过
echo.

REM 设置环境变量
echo [*] 设置环境变量...
if not exist ".env" (
    if exist "env.development.example" (
        copy env.development.example .env > nul
        echo [√] 已创建开发环境配置文件 .env
    ) else (
        copy env.example .env > nul
        echo [√] 已创建配置文件 .env
    )
) else (
    echo [i] 环境变量文件已存在，跳过创建
)
echo.

REM 创建必要的目录
echo [*] 创建必要的目录...
if not exist "data" mkdir data
if not exist "temp\outputs" mkdir temp\outputs
if not exist "temp\cache" mkdir temp\cache
if not exist "temp\logs" mkdir temp\logs
if not exist "temp\development" mkdir temp\development
if not exist "logs\postgres" mkdir logs\postgres
if not exist "logs\nginx" mkdir logs\nginx
if not exist "downloads" mkdir downloads
if not exist "backups" mkdir backups
echo [√] 目录创建完成
echo.

REM 启动服务
echo [*] 启动开发环境服务...
echo [i] 启动：PostgreSQL + pgAdmin
docker-compose --profile dev up -d
if errorlevel 1 (
    echo [错误] 服务启动失败
    pause
    exit /b 1
)
echo [√] 服务启动完成
echo.

REM 等待数据库就绪
echo [*] 等待PostgreSQL就绪...
set /a count=0
:wait_db
set /a count+=1
if %count% gtr 30 (
    echo [错误] PostgreSQL启动超时
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
echo [√] PostgreSQL已就绪
echo.

REM 初始化数据库表
echo [*] 检查数据库表...
docker-compose exec -T postgres psql -U erp_user -d xihong_erp -c "\dt" | findstr "accounts" > nul 2>&1
if errorlevel 1 (
    echo [*] 运行表初始化脚本...
    python docker\postgres\init-tables.py
    if errorlevel 1 (
        echo [警告] 数据库表初始化失败，请手动运行初始化脚本
    ) else (
        echo [√] 数据库表初始化完成
    )
) else (
    echo [i] 数据库表已存在，跳过初始化
)
echo.

REM 显示访问信息
echo ==========================================
echo 🎉 西虹ERP系统 - 开发环境启动成功！
echo ==========================================
echo.
echo 📊 服务访问地址：
echo   PostgreSQL:  localhost:5432
echo   pgAdmin:     http://localhost:5051
echo.
echo 🔐 数据库连接信息：
echo   数据库名: xihong_erp_dev
echo   用户名:   erp_dev
echo   密码:     dev_pass_2025
echo.
echo 🔐 pgAdmin登录信息：
echo   邮箱: dev@xihong.com
echo   密码: dev123
echo.
echo 📝 下一步：
echo   1. 启动后端: cd backend ^&^& uvicorn main:app --reload
echo   2. 启动前端: cd frontend ^&^& npm run dev
echo   3. 访问系统: http://localhost:5173
echo.
echo ⚙️  常用命令：
echo   查看日志: docker-compose logs -f postgres
echo   停止服务: docker-compose down
echo   重启服务: docker-compose restart postgres
echo.
echo ==========================================
echo.

pause

