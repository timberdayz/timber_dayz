@echo off
REM ===================================================
REM 停止本地PostgreSQL服务
REM ===================================================
REM 需要管理员权限运行
REM ===================================================

chcp 65001 > nul

echo ==========================================
echo 停止本地PostgreSQL服务
echo ==========================================
echo.
echo [INFO] 检测到本地PostgreSQL服务与Docker冲突
echo [INFO] 需要停止本地PostgreSQL服务
echo.
echo [WARNING] 此操作需要管理员权限
echo.

REM 检查管理员权限
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] 需要管理员权限
    echo.
    echo 请右键点击此文件，选择"以管理员身份运行"
    echo.
    pause
    exit /b 1
)

echo [OK] 已获得管理员权限
echo.

REM 查找并停止PostgreSQL服务
echo [INFO] 查找PostgreSQL服务...
sc query | findstr "postgresql" > nul 2>&1
if errorlevel 1 (
    echo [INFO] 未找到PostgreSQL服务名
    echo [INFO] 尝试常见服务名...
    
    REM 尝试常见的PostgreSQL服务名
    for %%s in (postgresql-x64-18 postgresql-x64-17 postgresql-x64-16 postgresql-x64-15 postgresql-x64-14 postgresql) do (
        sc query %%s > nul 2>&1
        if not errorlevel 1 (
            echo [INFO] 找到服务: %%s
            echo [INFO] 停止服务...
            net stop %%s
            if not errorlevel 1 (
                echo [OK] 服务已停止
                goto :success
            )
        )
    )
    
    echo [WARNING] 无法自动停止服务
    echo.
    echo 手动方法：
    echo 1. 打开"服务"管理器（services.msc）
    echo 2. 找到PostgreSQL相关服务
    echo 3. 右键停止
    echo.
    goto :end
)

:success
echo.
echo ==========================================
echo 成功停止本地PostgreSQL服务
echo ==========================================
echo.
echo [INFO] 现在可以使用Docker PostgreSQL
echo [INFO] 运行: start-docker-dev.bat
echo.

:end
pause

