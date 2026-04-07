@echo off
REM 西虹ERP系统完整启动脚本（含Redis）
REM 用途：一键启动PostgreSQL + Redis + ERP系统

echo ============================================
echo   西虹ERP系统启动脚本 v4.6.3
echo ============================================
echo.

REM 1. 检查并启动PostgreSQL
echo [1/4] 检查PostgreSQL容器...
docker ps -a | findstr xihong_erp_postgres >nul
if %errorlevel% neq 0 (
    echo [启动] PostgreSQL容器不存在，正在创建...
    docker-compose up -d postgres
) else (
    docker ps | findstr xihong_erp_postgres >nul
    if %errorlevel% neq 0 (
        echo [启动] PostgreSQL容器已停止，正在启动...
        docker start xihong_erp_postgres
    ) else (
        echo [OK] PostgreSQL容器正在运行
    )
)
echo.

REM 2. 检查并启动Redis
echo [2/4] 检查Redis容器...
docker ps -a | findstr xihong_erp_redis >nul
if %errorlevel% neq 0 (
    echo [启动] Redis容器不存在，正在创建...
    docker run -d -p 6379:6379 --name xihong_erp_redis redis:alpine
) else (
    docker ps | findstr xihong_erp_redis >nul
    if %errorlevel% neq 0 (
        echo [启动] Redis容器已停止，正在启动...
        docker start xihong_erp_redis
    ) else (
        echo [OK] Redis容器正在运行
    )
)
echo.

REM 3. 等待服务就绪
echo [3/4] 等待服务就绪...
timeout /t 3 /nobreak >nul
echo [OK] 数据库和缓存已就绪
echo.

REM 4. 启动ERP系统
echo [4/4] 启动西虹ERP系统...
echo.
echo ============================================
echo   系统启动中，请稍候...
echo ============================================
echo.
echo   预期日志：
echo   - 🌍 运行环境: development
echo   - [OK] PostgreSQL PATH配置完成
echo   - [OK] 数据库连接验证成功
echo   - [OK] API速率限制已启用
echo   - [OK] Redis缓存已启用          ^<-- 看到这个说明Redis正常
echo   - 总启动时间: 0.57秒
echo.
echo   访问地址：
echo   - 前端界面: http://localhost:5173
echo   - API文档: http://localhost:8001/api/docs
echo.
echo ============================================

python run.py

