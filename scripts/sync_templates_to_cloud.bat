@echo off
REM 模板数据云端同步脚本（方案A：压缩传输优化）
REM 使用批处理文件调用PowerShell脚本，避免编码问题

cd /d "%~dp0\.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0sync_templates_to_cloud.ps1" %*
