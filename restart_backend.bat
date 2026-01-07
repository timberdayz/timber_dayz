@echo off
chcp 65001 >nul
echo ==================================================
echo [1/3] Stopping backend...
echo ==================================================
taskkill /f /im python.exe /fi "WINDOWTITLE eq *uvicorn*" 2>nul
REM v4.19.6: 同时停止Celery worker（如果运行）
taskkill /f /im python.exe /fi "WINDOWTITLE eq *celery*" 2>nul

timeout /t 2 /nobreak >nul

echo.
echo ==================================================
echo [2/3] Starting backend...
echo ==================================================
cd backend
start "Backend Service" cmd /k "uvicorn main:app --reload --port 8001"

echo.
echo ==================================================
echo [3/3] Done!
echo ==================================================
echo Backend restarting... Please wait 5 seconds
echo Then refresh browser (F5)
echo.
echo [提示] Celery Worker未自动重启，如需启动请运行:
echo        python -m celery -A backend.celery_app worker --loglevel=info --queues=data_sync,scheduled,data_processing --pool=solo --concurrency=4
echo        或使用: python run.py --backend-only
echo ==================================================
timeout /t 5

