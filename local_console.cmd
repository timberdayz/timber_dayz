@echo off
setlocal
cd /d "%~dp0"

where pythonw.exe >nul 2>&1
if not errorlevel 1 (
    start "" /B pythonw.exe "%~dp0scripts\local_console.py"
    exit /b 0
)

where python.exe >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH.
    echo [INFO] Install or activate the project Python runtime, then retry.
    pause
    exit /b 1
)

start "Xihong ERP Local Console" /MIN python.exe "%~dp0scripts\local_console.py"
exit /b 0
