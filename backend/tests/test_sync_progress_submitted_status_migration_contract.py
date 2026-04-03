from pathlib import Path
import os
import subprocess
import sys
import time

import psycopg2


CURRENT_REVISION = "20260403_sync_nulls"


def _find_sync_progress_submitted_migration() -> Path:
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*sync*progress*submitted*.py"))
    assert matches, "expected a sync-progress submitted-status migration in migrations/versions"
    return matches[-1]


def test_sync_progress_submitted_status_migration_exists():
    _find_sync_progress_submitted_migration()


def test_sync_progress_submitted_status_migration_mentions_constraint_and_status():
    migration_path = _find_sync_progress_submitted_migration()
    source = migration_path.read_text(encoding="utf-8")

    assert "sync_progress_tasks" in source
    assert "chk_sync_progress_status" in source
    assert "submitted" in source


def test_sync_progress_submitted_status_migration_allows_legacy_status_on_postgres():
    admin_conn = psycopg2.connect(
        host="127.0.0.1",
        port=15432,
        user="erp_user",
        password="erp_pass_2025",
        dbname="postgres",
    )
    admin_conn.autocommit = True
    rehearsal_db = f"xihong_erp_sync_status_{int(time.time())}"

    try:
        with admin_conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {rehearsal_db}")
            cur.execute(f"CREATE DATABASE {rehearsal_db}")

        conn = psycopg2.connect(
            host="127.0.0.1",
            port=15432,
            user="erp_user",
            password="erp_pass_2025",
            dbname=rehearsal_db,
        )
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("CREATE SCHEMA IF NOT EXISTS core")
                    cur.execute(
                        """
                        CREATE TABLE core.alembic_version (
                            version_num VARCHAR(32) NOT NULL PRIMARY KEY
                        )
                        """
                    )
                    cur.execute(
                        "INSERT INTO core.alembic_version(version_num) VALUES (%s)",
                        (CURRENT_REVISION,),
                    )
                    cur.execute(
                        """
                        CREATE TABLE core.sync_progress_tasks (
                            task_id VARCHAR(100) PRIMARY KEY,
                            task_type VARCHAR(50) NOT NULL,
                            total_files INTEGER NOT NULL DEFAULT 0,
                            processed_files INTEGER NOT NULL DEFAULT 0,
                            current_file VARCHAR(500),
                            status VARCHAR(20) NOT NULL DEFAULT 'pending',
                            total_rows INTEGER NOT NULL DEFAULT 0,
                            processed_rows INTEGER NOT NULL DEFAULT 0,
                            valid_rows INTEGER NOT NULL DEFAULT 0,
                            error_rows INTEGER NOT NULL DEFAULT 0,
                            quarantined_rows INTEGER NOT NULL DEFAULT 0,
                            file_progress DOUBLE PRECISION NOT NULL DEFAULT 0,
                            row_progress DOUBLE PRECISION NOT NULL DEFAULT 0,
                            start_time TIMESTAMPTZ NOT NULL DEFAULT now(),
                            end_time TIMESTAMPTZ,
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                            errors JSONB,
                            warnings JSONB,
                            task_details JSONB,
                            CONSTRAINT chk_sync_progress_status
                                CHECK (status IN ('pending', 'processing', 'completed', 'failed'))
                        )
                        """
                    )
                    cur.execute(
                        """
                        INSERT INTO core.sync_progress_tasks (
                            task_id, task_type, status
                        ) VALUES (
                            'legacy-sync-task', 'single_file', 'pending'
                        )
                        """
                    )
        finally:
            conn.close()

        env = os.environ.copy()
        env["DATABASE_URL"] = (
            f"postgresql://erp_user:erp_pass_2025@127.0.0.1:15432/{rehearsal_db}"
        )
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
            cwd=str(Path.cwd()),
            env=env,
            capture_output=True,
            text=True,
            timeout=240,
        )
        assert result.returncode == 0, (
            f"alembic upgrade failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

        conn = psycopg2.connect(
            host="127.0.0.1",
            port=15432,
            user="erp_user",
            password="erp_pass_2025",
            dbname=rehearsal_db,
        )
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE core.sync_progress_tasks
                        SET status = 'submitted'
                        WHERE task_id = 'legacy-sync-task'
                        """
                    )
        finally:
            conn.close()
    finally:
        with admin_conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {rehearsal_db}")
        admin_conn.close()
