@echo off
REM 西虹ERP系统快速启动脚本（仅PostgreSQL）
REM 用途：开发环境快速启动，不启动Redis

echo ============================================
echo   西虹ERP系统快速启动 v4.6.3
echo ============================================
echo.

REM 1. 检查并启动PostgreSQL
echo [1/2] 检查PostgreSQL容器...
docker ps | findstr xihong_erp_postgres >nul
if %errorlevel% neq 0 (
    echo [启动] PostgreSQL未运行，正在启动...
    docker start xihong_erp_postgres 2>nul || docker-compose up -d postgres
) else (
    echo [OK] PostgreSQL容器正在运行
)
echo.

REM 2. 启动ERP系统
echo [2/2] 启动西虹ERP系统...
echo.
echo ============================================
echo   快速启动模式（无Redis缓存）
echo ============================================
echo.
echo   预期日志：
echo   - 🌍 运行环境: development
echo   - [OK] 数据库连接验证成功
echo   - [OK] API速率限制已启用
echo   - [SKIP] Redis缓存未启用       ^<-- 正常，开发环境可选
echo.
echo   访问地址：
echo   - 前端: http://localhost:5173
echo.
echo ============================================

python run.py

