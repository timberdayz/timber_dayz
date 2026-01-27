#!/bin/bash
# 西虹ERP系统 - 后端容器入口脚本
# 启动前自动执行数据库迁移，再执行传入的命令（gunicorn/uvicorn 等）
set -e

echo "[INFO] Running database migrations..."
cd /app
alembic upgrade head || {
    echo "[WARNING] Migration failed, starting service anyway (check logs)"
}

echo "[INFO] Starting backend service..."
exec "$@"
