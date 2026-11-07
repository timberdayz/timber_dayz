"""data-sync schema repair 的契约守护。

⚠️ 迁移链的口径(2026-08 起)
-------------------------
* ``migrations/versions/`` 是**只读历史链**: ``current_migrations/README.md``
  明确写了它「不再被部署/启动入口使用」。本文件里两条**静态**用例继续钉住
  历史链里那份 repair 迁移(它是该口径的出处, 文件仍在仓库里)。
* **当前唯一事实源**是 ``current_migrations/``(``alembic-current.ini``),
  它的静态基线 ``current_schema_20260805`` 已经把 repair 的结果固化下来:
  ``core.data_quarantine`` / ``core.staging_orders`` /
  ``core.staging_product_metrics`` 直接带上了新列。

所以两条**行为**用例改为在临时库里重放**当前链的基线**, 然后断言:
1. repair 需要的列确实存在;
2. 现在的写入形状(INSERT)能被当前 schema 接受。

旧链已经不能在空库上重放(``migrations/versions/20260130_v4_21_0_hr_module_tables.py``
会去 ALTER 一个还不存在的 ``a_class.employees``)⇒ 继续跑旧链已经没有意义。
"""

from pathlib import Path
import os
import subprocess
import sys
import time

import psycopg2


CURRENT_REVISION = "20260402_main_shop_accounts"

#: 当前事实源: 独立迁移链 + 它的静态生产基线
CURRENT_CHAIN_CONFIG = "alembic-current.ini"
CURRENT_BASELINE_REVISION = "current_schema_20260805"


def _find_data_sync_schema_repair_migration() -> Path:
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*data_sync*schema*repair*.py"))
    assert (
        matches
    ), "expected a data-sync schema repair migration in migrations/versions"
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


def test_data_sync_schema_repair_migration_exists():
    _find_data_sync_schema_repair_migration()


def test_data_sync_schema_repair_migration_mentions_target_tables_and_columns():
    migration_path = _find_data_sync_schema_repair_migration()
    source = migration_path.read_text(encoding="utf-8")

    assert "data_quarantine" in source
    assert "staging_orders" in source
    assert "staging_product_metrics" in source
    assert "catalog_file_id" in source
    assert "source_file" in source
    assert "file_id" in source
    assert "platform_code" in source


def test_data_sync_schema_repair_columns_present_in_current_schema_baseline():
    """当前事实源(``current_migrations`` 基线)必须带上 repair 的全部列。"""
    admin_conn = psycopg2.connect(
        host="127.0.0.1",
        port=15432,
        user="erp_user",
        password="erp_pass_2025",
        dbname="postgres",
    )
    admin_conn.autocommit = True
    rehearsal_db = f"xihong_erp_sync_repair_{int(time.time())}"

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
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'core' AND table_name = 'data_quarantine'
                        ORDER BY column_name
                        """
                    )
                    data_quarantine_columns = {row[0] for row in cur.fetchall()}

                    cur.execute(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'core' AND table_name = 'staging_orders'
                        ORDER BY column_name
                        """
                    )
                    staging_orders_columns = {row[0] for row in cur.fetchall()}

                    cur.execute(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'core' AND table_name = 'staging_product_metrics'
                        ORDER BY column_name
                        """
                    )
                    staging_metrics_columns = {row[0] for row in cur.fetchall()}

            assert {
                "source_file",
                "catalog_file_id",
                "row_number",
                "row_data",
                "error_type",
                "error_msg",
                "platform_code",
                "shop_id",
                "data_domain",
                "is_resolved",
                "resolved_at",
                "resolution_note",
            }.issubset(data_quarantine_columns)
            assert {"platform_code", "ingest_task_id", "file_id"}.issubset(
                staging_orders_columns
            )
            assert {
                "platform_code",
                "platform_sku",
                "ingest_task_id",
                "file_id",
            }.issubset(staging_metrics_columns)
        finally:
            conn.close()
    finally:
        with admin_conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {rehearsal_db}")
        admin_conn.close()


def test_data_sync_schema_repair_allows_current_insert_shapes_on_postgres_db():
    """当前写入形状必须能被当前 schema 接受(逐列对齐 + 真写一遍)。"""
    admin_conn = psycopg2.connect(
        host="127.0.0.1",
        port=15432,
        user="erp_user",
        password="erp_pass_2025",
        dbname="postgres",
    )
    admin_conn.autocommit = True
    rehearsal_db = f"xihong_erp_sync_insert_{int(time.time())}"

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
                        INSERT INTO public.catalog_files (file_name, file_path)
                        VALUES ('smoke.xlsx', '/tmp/smoke.xlsx')
                        RETURNING id
                        """
                    )
                    file_id = cur.fetchone()[0]
                    cur.execute(
                        """
                        INSERT INTO core.data_quarantine (
                            source_file,
                            catalog_file_id,
                            row_number,
                            row_data,
                            error_type,
                            error_msg,
                            platform_code,
                            data_domain,
                            is_resolved
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            "smoke.xlsx",
                            file_id,
                            1,
                            '{"row": 1}',
                            "validation_error",
                            "smoke",
                            "tiktok",
                            "orders",
                            False,
                        ),
                    )
                    cur.execute(
                        """
                        INSERT INTO core.staging_orders (
                            platform_code,
                            shop_id,
                            order_id,
                            order_data,
                            ingest_task_id,
                            file_id
                        ) VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                        """,
                        (
                            "tiktok",
                            "shop-a",
                            "order-a",
                            '{"id": "order-a"}',
                            "task-a",
                            file_id,
                        ),
                    )
                    cur.execute(
                        """
                        INSERT INTO core.staging_product_metrics (
                            platform_code,
                            shop_id,
                            platform_sku,
                            metric_data,
                            ingest_task_id,
                            file_id
                        ) VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                        """,
                        (
                            "tiktok",
                            "shop-a",
                            "sku-a",
                            '{"id": "sku-a"}',
                            "task-a",
                            file_id,
                        ),
                    )
        finally:
            conn.close()
    finally:
        with admin_conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {rehearsal_db}")
        admin_conn.close()
