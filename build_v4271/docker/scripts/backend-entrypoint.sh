#!/bin/bash
# Backend container entrypoint script
# Run database migrations before starting the service
set -e

echo "[INFO] Running database migrations..."
cd /app
# [FIX] 使用 heads（复数）以支持多头迁移分支；与 deploy_remote_production.sh Phase 2 一致
if ! alembic upgrade heads; then
    echo "[ERROR] Migration failed (alembic upgrade heads). Start aborted."
    echo "[INFO] Check DATABASE_URL and run: alembic upgrade heads"
    exit 1
fi

echo "[INFO] Starting backend service..."
exec "$@"