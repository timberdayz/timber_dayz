@echo off
REM ===================================================
REM 西虹ERP系统 - 停止脚本（Windows）
REM ===================================================
REM 功能：优雅停止所有Docker服务
REM 使用方式：docker\scripts\stop.bat
REM ===================================================

chcp 65001 > nul
setlocal enabledelayedexpansion

cls
echo ==========================================
echo 西虹ERP系统 - 停止服务
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

REM 显示当前运行的容器
echo 当前运行的容器：
docker-compose ps
echo.

REM 确认停止
set /p confirm="确认停止所有服务? (Y/N): "
if /i not "%confirm%"=="Y" (
    echo [i] 操作已取消
    pause
    exit /b 0
)

REM 停止服务
echo.
echo [*] 正在停止服务...
docker-compose down
if errorlevel 1 (
    echo [错误] 停止服务失败
    pause
    exit /b 1
)
echo [√] 服务已停止
echo.

REM 询问是否清理资源
echo [警告] 清理资源
echo [i] 这将删除所有容器和网络，但保留数据卷和镜像
echo.
set /p confirm="是否清理Docker资源? (Y/N): "
if /i "%confirm%"=="Y" (
    docker-compose down
    echo [√] 资源已清理
    echo.
    
    echo [警告] 是否同时删除数据卷? ⚠️  这将删除所有数据!
    set /p confirm_volumes="确认删除数据卷? (Y/N): "
    if /i "!confirm_volumes!"=="Y" (
        docker-compose down -v
        echo [警告] 数据卷已删除
    )
)

REM 显示信息
echo.
echo ==========================================
echo 服务停止完成
echo ==========================================
echo.
echo 📊 当前状态：
docker-compose ps 2>nul || echo 所有服务已停止
echo.
echo 💾 数据保留：
docker volume ls | findstr "xihong_erp_postgres_data" >nul 2>&1
if errorlevel 1 (
    echo   - PostgreSQL数据卷: ✗ 已删除
) else (
    echo   - PostgreSQL数据卷: ✓ 保留
)
if exist "data" (
    echo   - 应用数据目录: ✓ 保留
) else (
    echo   - 应用数据目录: ✗ 不存在
)
if exist "logs" (
    echo   - 日志目录: ✓ 保留
) else (
    echo   - 日志目录: ✗ 不存在
)
echo.
echo 🔄 重启服务：
echo   开发模式: docker\scripts\start-dev.bat
echo   生产模式: docker\scripts\start-prod.bat
echo.
echo ==========================================
echo.

pause

