#!/bin/bash
# Backend container entrypoint script
# Optionally run database migrations before starting the service
set -e

cd /app

should_run_migrations="${RUN_MIGRATIONS:-0}"

is_backend_service_command() {
    case "$1" in
        gunicorn|uvicorn)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

case "${should_run_migrations}" in
    1|true|TRUE|yes|YES)
        echo "[INFO] Running fail-closed current-schema migration..."
        if ! python3 /app/scripts/run_current_schema_migrations.py; then
            echo "[ERROR] Current-schema migration failed. Start aborted."
            echo "[INFO] Check DATABASE_URL and the current-schema source contract."
            exit 1
        fi

        ;;
    *)
        echo "[INFO] Skipping database migrations (RUN_MIGRATIONS=${should_run_migrations})."
        ;;
esac

if [ "$#" -gt 0 ] && is_backend_service_command "$1"; then
    echo "[INFO] Starting backend service..."
else
    echo "[INFO] Running one-off command: $*"
fi
exec "$@"
