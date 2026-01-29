#!/bin/bash
# Backend container entrypoint script
# Run database migrations before starting the service
set -e

echo "[INFO] Running database migrations..."
cd /app
alembic upgrade head || {
    echo "[WARNING] Migration failed, starting service anyway (check logs)"
}

echo "[INFO] Starting backend service..."
exec "$@"