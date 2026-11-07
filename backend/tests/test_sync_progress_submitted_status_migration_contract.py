"""sync-progress ``submitted`` 状态的契约守护。

⚠️ 迁移链的口径(2026-08 起)
-------------------------
* ``migrations/versions/`` 是**只读历史链**; 两条**静态**用例继续钉住历史链里
  那份 ``submitted`` 迁移(它是该口径的出处, 文件仍在仓库里)。
* **当前唯一事实源**是 ``current_migrations/``(``alembic-current.ini``): 静态基线
  ``current_schema_20260805`` 里 ``core.sync_progress_tasks`` 的
  ``chk_sync_progress_status`` 约束已经包含 ``submitted``。

所以行为用例改为在临时库上重放**当前链的基线**, 断言:
1. 约束确实接受 ``submitted``;
2. 历史遗留的 ``pending`` 任务能就地改成 ``submitted``。
"""

from pathlib import Path
import os
import subprocess
import sys
import time

import psycopg2


CURRENT_REVISION = "20260403_sync_nulls"

#: 当前事实源: 独立迁移链 + 它的静态生产基线
CURRENT_CHAIN_CONFIG = "alembic-current.ini"
CURRENT_BASELINE_REVISION = "current_schema_20260805"


def _find_sync_progress_submitted_migration() -> Path:
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*sync*progress*submitted*.py"))
    assert matches, "expected a sync-progress submitted-status migration in migrations/versions"
    return matches[-1]


def _upgrade_current_baseline(database_url: str) -> subprocess.CompletedProcess:
    """在临时库上重放当前链的静态基线。"""
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            CURRENT_CHAIN_CONFIG,
            "upgrade",
            CURRENT_BASELINE_REVISION,
        ],
        cwd=str(Path.cwd()),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )


def test_sync_progress_submitted_status_migration_exists():
    _find_sync_progress_submitted_migration()


def test_sync_progress_submitted_status_migration_mentions_constraint_and_status():
    migration_path = _find_sync_progress_submitted_migration()
    source = migration_path.read_text(encoding="utf-8")

    assert "sync_progress_tasks" in source
    assert "chk_sync_progress_status" in source
    assert "submitted" in source


def test_sync_progress_submitted_status_migration_allows_legacy_status_on_postgres():
    """当前 schema 的状态约束必须接受 ``submitted``, 且能就地改写历史任务。"""
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

        database_url = (
            f"postgresql://erp_user:erp_pass_2025@127.0.0.1:15432/{rehearsal_db}"
        )
        result = _upgrade_current_baseline(database_url)

        assert result.returncode == 0, (
            "alembic upgrade failed\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
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
                        SELECT pg_get_constraintdef(oid)
                        FROM pg_constraint
                        WHERE conrelid = 'core.sync_progress_tasks'::regclass
                          AND conname = 'chk_sync_progress_status'
                        """
                    )
                    row = cur.fetchone()
                    assert row is not None, "chk_sync_progress_status 约束不存在"
                    constraint_definition = row[0]
                    assert "submitted" in constraint_definition

                    cur.execute(
                        """
                        INSERT INTO core.sync_progress_tasks (
                            task_id, task_type, status,
                            total_files, processed_files,
                            total_rows, processed_rows,
                            valid_rows, error_rows, quarantined_rows,
                            file_progress, row_progress,
                            start_time, updated_at
                        ) VALUES (
                            'legacy-sync-task', 'single_file', 'pending',
                            0, 0,
                            0, 0,
                            0, 0, 0,
                            0, 0,
                            now(), now()
                        )
                        """
                    )
                    cur.execute(
                        """
                        UPDATE core.sync_progress_tasks
                        SET status = 'submitted'
                        WHERE task_id = 'legacy-sync-task'
                        """
                    )
                    cur.execute(
                        """
                        SELECT status
                        FROM core.sync_progress_tasks
                        WHERE task_id = 'legacy-sync-task'
                        """
                    )
                    assert cur.fetchone()[0] == "submitted"
        finally:
            conn.close()
    finally:
        with admin_conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {rehearsal_db}")
        admin_conn.close()
