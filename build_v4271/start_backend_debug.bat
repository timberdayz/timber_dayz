@echo off
cd /d F:\Vscode\python_programme\AI_code\xihong_erp\backend
echo Starting backend server...
python -m uvicorn main:app --host 0.0.0.0 --port 8001
pause

