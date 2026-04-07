@echo off
REM ===================================================
REM Docker镜像加速器配置助手
REM ===================================================

chcp 65001 > nul
cls

echo ==========================================
echo Docker镜像加速器配置助手
echo ==========================================
echo.
echo 检测到Docker镜像拉取超时问题
echo 这是因为Docker Hub在中国访问很慢
echo.
echo 解决方案：
echo.
echo 1. 配置Docker Desktop镜像加速器
echo    - 打开Docker Desktop
echo    - 点击右上角齿轮图标 ⚙️
echo    - 选择 Docker Engine
echo    - 添加以下配置：
echo.
echo {
echo   "registry-mirrors": [
echo     "https://docker.mirrors.sjtug.sjtu.edu.cn",
echo     "https://docker.m.daocloud.io",
echo     "https://dockerhub.icu"
echo   ]
echo }
echo.
echo    - 点击 Apply ^& Restart
echo.
echo 2. 或者手动拉取镜像
echo.
set /p choice="是否现在手动拉取镜像？(Y/N): "
if /i "%choice%"=="Y" (
    echo.
    echo [*] 正在拉取PostgreSQL镜像...
    docker pull postgres:15-alpine
    if errorlevel 1 (
        echo [错误] 拉取失败，请先配置镜像加速器
        echo.
        echo 详细配置步骤请查看：DOCKER_MIRROR_SETUP.md
        pause
        exit /b 1
    )
    
    echo.
    echo [*] 正在拉取pgAdmin镜像...
    docker pull dpage/pgadmin4:latest
    if errorlevel 1 (
        echo [警告] pgAdmin拉取失败，但可以继续
    )
    
    echo.
    echo [√] 镜像拉取完成！
    echo.
    echo 现在可以运行：
    echo   start-docker-dev.bat
    echo.
) else (
    echo.
    echo 请按照以下步骤手动配置：
    echo.
    echo 1. 打开Docker Desktop
    echo 2. 设置 -^> Docker Engine
    echo 3. 添加镜像加速配置
    echo 4. Apply ^& Restart
    echo.
    echo 详细配置步骤：DOCKER_MIRROR_SETUP.md
    echo.
    start DOCKER_MIRROR_SETUP.md
)

pause

