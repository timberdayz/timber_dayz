#!/bin/bash
# Backend container entrypoint script
# Optionally run database migrations before starting the service
set -e

cd /app

should_run_migrations="${RUN_MIGRATIONS:-0}"

case "${should_run_migrations}" in
    1|true|TRUE|yes|YES)
        echo "[INFO] Running database migrations..."
        if ! alembic upgrade heads; then
            echo "[ERROR] Migration failed (alembic upgrade heads). Start aborted."
            echo "[INFO] Check DATABASE_URL and run: alembic upgrade heads"
            exit 1
        fi

        if [ "$#" -ge 3 ] && [ "$1" = "alembic" ] && [ "$2" = "upgrade" ] && [ "$3" = "heads" ]; then
            echo "[INFO] Migration job completed successfully."
            exit 0
        fi
        ;;
    *)
        echo "[INFO] Skipping database migrations (RUN_MIGRATIONS=${should_run_migrations})."
        ;;
esac

echo "[INFO] Starting backend service..."
exec "$@"
