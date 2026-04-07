@echo off
REM ===================================================
REM 西虹ERP系统 - 环境检查脚本（Windows）
REM ===================================================
REM 功能：检查Docker部署所需的环境和依赖
REM 使用方式：docker\scripts\check-requirements.bat
REM ===================================================

chcp 65001 > nul
setlocal enabledelayedexpansion

set total_checks=0
set passed_checks=0
set failed_checks=0

cls
echo ==========================================
echo 西虹ERP系统 - Docker环境检查
echo ==========================================
echo.
echo 检查时间: %date% %time%
echo.

REM 自动切换到项目根目录
if exist "..\..\docker-compose.yml" (
    cd ..\..
    echo [i] 已自动切换到项目根目录
    echo.
)

REM 1. 检查Docker
echo ==========================================
echo Docker环境检查
echo ==========================================
echo.

set /a total_checks+=1
echo [*] 检查 Docker是否安装...
docker --version > nul 2>&1
if errorlevel 1 (
    echo [✗] FAIL - Docker未安装
    echo     请访问 https://www.docker.com/get-started 安装Docker Desktop
    set /a failed_checks+=1
) else (
    for /f "tokens=*" %%i in ('docker --version') do set docker_ver=%%i
    echo [✓] OK - !docker_ver!
    set /a passed_checks+=1
)

set /a total_checks+=1
echo [*] 检查 Docker是否运行...
docker info > nul 2>&1
if errorlevel 1 (
    echo [✗] FAIL - Docker未运行
    echo     请启动Docker Desktop应用
    set /a failed_checks+=1
) else (
    echo [✓] OK
    set /a passed_checks+=1
)

set /a total_checks+=1
echo [*] 检查 Docker Compose是否安装...
docker-compose --version > nul 2>&1
if errorlevel 1 (
    echo [✗] FAIL - Docker Compose未安装
    set /a failed_checks+=1
) else (
    for /f "tokens=*" %%i in ('docker-compose --version') do set compose_ver=%%i
    echo [✓] OK - !compose_ver!
    set /a passed_checks+=1
)
echo.

REM 2. 检查系统资源
echo ==========================================
echo 系统资源检查
echo ==========================================
echo.

set /a total_checks+=1
echo [*] 检查 可用磁盘空间...
for /f "tokens=3" %%a in ('dir /-c ^| find "bytes free"') do set free_space=%%a
echo [✓] OK - 可用空间: !free_space! 字节
set /a passed_checks+=1
echo.

REM 3. 检查端口占用
echo ==========================================
echo 端口占用检查
echo ==========================================
echo.

call :check_port 5432 "PostgreSQL"
call :check_port 8001 "Backend API"
call :check_port 5174 "Frontend"
call :check_port 5051 "pgAdmin"
echo.

REM 4. 检查项目文件
echo ==========================================
echo 项目文件检查
echo ==========================================
echo.

call :check_file "docker-compose.yml"
call :check_file "Dockerfile.backend"
call :check_file "Dockerfile.frontend"
call :check_file "env.example"
echo.

REM 5. 检查Docker配置语法
echo ==========================================
echo Docker配置语法检查
echo ==========================================
echo.

set /a total_checks+=1
echo [*] 检查 docker-compose.yml语法...
docker-compose config --quiet > nul 2>&1
if errorlevel 1 (
    echo [✗] FAIL - 配置文件语法错误
    docker-compose config 2>&1
    set /a failed_checks+=1
) else (
    echo [✓] OK
    set /a passed_checks+=1
)
echo.

REM 6. 检查Python环境
echo ==========================================
echo Python环境检查
echo ==========================================
echo.

set /a total_checks+=1
echo [*] 检查 Python是否安装...
python --version > nul 2>&1
if errorlevel 1 (
    echo [⚠] WARNING - Python未安装（如需本地开发则需要）
) else (
    for /f "tokens=*" %%i in ('python --version') do set python_ver=%%i
    echo [✓] OK - !python_ver!
    set /a passed_checks+=1
)

set /a total_checks+=1
echo [*] 检查 pip是否安装...
pip --version > nul 2>&1
if errorlevel 1 (
    echo [⚠] WARNING - pip未安装（如需本地开发则需要）
) else (
    echo [✓] OK
    set /a passed_checks+=1
)
echo.

REM 7. 检查Node.js环境
echo ==========================================
echo Node.js环境检查
echo ==========================================
echo.

set /a total_checks+=1
echo [*] 检查 Node.js是否安装...
node --version > nul 2>&1
if errorlevel 1 (
    echo [⚠] WARNING - Node.js未安装（如需本地前端开发则需要）
) else (
    for /f "tokens=*" %%i in ('node --version') do set node_ver=%%i
    echo [✓] OK - !node_ver!
    set /a passed_checks+=1
)

set /a total_checks+=1
echo [*] 检查 npm是否安装...
npm --version > nul 2>&1
if errorlevel 1 (
    echo [⚠] WARNING - npm未安装（如需本地前端开发则需要）
) else (
    for /f "tokens=*" %%i in ('npm --version') do set npm_ver=%%i
    echo [✓] OK - v!npm_ver!
    set /a passed_checks+=1
)
echo.

REM 生成检查报告
echo ==========================================
echo 检查报告
echo ==========================================
echo.
echo 总检查项: !total_checks!
echo 通过: !passed_checks!
echo 失败: !failed_checks!
echo.

if !failed_checks! EQU 0 (
    echo [✓] 所有关键检查通过，可以开始Docker部署！
    echo.
    echo 下一步：
    echo   1. 配置环境变量: copy env.example .env
    echo   2. 启动开发环境: docker\scripts\start-dev.bat
    echo   3. 或启动生产环境: docker\scripts\start-prod.bat
    echo.
    pause
    exit /b 0
) else (
    echo [✗] 有 !failed_checks! 项检查失败
    echo.
    echo 请解决上述问题后再次运行此脚本
    echo.
    pause
    exit /b 1
)

REM ===================================================
REM 辅助函数
REM ===================================================

:check_port
set /a total_checks+=1
echo [*] 检查 端口 %1 (%~2)...
netstat -ano | findstr ":%1 " | findstr "LISTENING" > nul 2>&1
if errorlevel 1 (
    echo [✓] OK - 端口可用
    set /a passed_checks+=1
) else (
    echo [✗] FAIL - 端口已被占用
    netstat -ano | findstr ":%1 "
    set /a failed_checks+=1
)
goto :eof

:check_file
set /a total_checks+=1
echo [*] 检查 %~1...
if exist "%~1" (
    echo [✓] OK
    set /a passed_checks+=1
) else (
    echo [✗] FAIL - 文件不存在
    set /a failed_checks+=1
)
goto :eof

