@echo off
setlocal
title Xihong ERP Local Console
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"

where python.exe >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH.
    echo [INFO] Install or activate the project Python runtime, then retry.
    pause
    exit /b 1
)

echo [Local Console] Starting visible controller...
python.exe -u "%~dp0scripts\local_console.py"
set "exit_code=%ERRORLEVEL%"
if not "%exit_code%"=="0" (
    echo [ERROR] Local console exited with code %exit_code%.
    echo [INFO] Review the message above and the logs under logs\local-console\.
    pause
)
exit /b %exit_code%
