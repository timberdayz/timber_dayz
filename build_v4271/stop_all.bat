@echo off
chcp 65001 >nul
echo ============================================
echo    西虹ERP系统 - 停止所有服务
echo ============================================
echo.

echo [1/2] 停止后端服务...
taskkill /F /FI "WINDOWTITLE eq 西虹ERP后端" >nul 2>&1
if "%ERRORLEVEL%"=="0" (
    echo [OK] 后端服务已停止
) else (
    echo [提示] 后端服务未运行
)

echo.
echo [2/2] 停止前端服务...
taskkill /F /FI "WINDOWTITLE eq 西虹ERP前端" >nul 2>&1
if "%ERRORLEVEL%"=="0" (
    echo [OK] 前端服务已停止
) else (
    echo [提示] 前端服务未运行
)

echo.
echo ============================================
echo    所有服务已停止
echo ============================================
echo.
pause

