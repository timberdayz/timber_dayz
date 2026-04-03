from pathlib import Path
import os
import subprocess
import sys
import time

import psycopg2


CURRENT_REVISION = "20260402_main_shop_accounts"


def _find_data_sync_schema_repair_migration() -> Path:
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*data_sync*schema*repair*.py"))
    assert matches, "expected a data-sync schema repair migration in migrations/versions"
    return matches[-1]


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


def test_data_sync_schema_repair_migration_applies_to_drifted_postgres_db():
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
                        CREATE TABLE public.catalog_files (
                            id SERIAL PRIMARY KEY
                        )
                        """
                    )
                    cur.execute(
                        """
                        CREATE TABLE core.data_quarantine (
                            id SERIAL PRIMARY KEY,
                            platform VARCHAR(50),
                            data_type VARCHAR(50),
                            quarantine_reason TEXT,
                            raw_data JSONB,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                        )
                        """
                    )
                    cur.execute(
                        """
                        CREATE TABLE core.staging_orders (
                            id SERIAL PRIMARY KEY,
                            platform VARCHAR(32),
                            shop_id VARCHAR(64),
                            order_id VARCHAR(128),
                            order_data JSONB NOT NULL,
                            processed BOOLEAN DEFAULT FALSE,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                        )
                        """
                    )
                    cur.execute(
                        """
                        CREATE TABLE core.staging_product_metrics (
                            id SERIAL PRIMARY KEY,
                            platform VARCHAR(32),
                            shop_id VARCHAR(64),
                            product_sku VARCHAR(64),
                            metric_data JSONB NOT NULL,
                            processed BOOLEAN DEFAULT FALSE,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
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
            assert {"platform_code", "ingest_task_id", "file_id"}.issubset(staging_orders_columns)
            assert {"platform_code", "platform_sku", "ingest_task_id", "file_id"}.issubset(
                staging_metrics_columns
            )
        finally:
            conn.close()
    finally:
        with admin_conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {rehearsal_db}")
        admin_conn.close()


def test_data_sync_schema_repair_allows_current_insert_shapes_on_postgres_db():
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
                        CREATE TABLE public.catalog_files (
                            id SERIAL PRIMARY KEY
                        )
                        """
                    )
                    cur.execute("INSERT INTO public.catalog_files DEFAULT VALUES RETURNING id")
                    file_id = cur.fetchone()[0]
                    cur.execute(
                        """
                        CREATE TABLE core.data_quarantine (
                            id SERIAL PRIMARY KEY,
                            platform VARCHAR(50) NOT NULL,
                            data_type VARCHAR(50) NOT NULL,
                            quarantine_reason TEXT,
                            raw_data JSONB,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                        )
                        """
                    )
                    cur.execute(
                        """
                        CREATE TABLE core.staging_orders (
                            id SERIAL PRIMARY KEY,
                            platform VARCHAR(32) NOT NULL,
                            shop_id VARCHAR(64) NOT NULL,
                            order_id VARCHAR(128) NOT NULL,
                            order_data JSONB,
                            processed BOOLEAN DEFAULT FALSE,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                        )
                        """
                    )
                    cur.execute(
                        """
                        CREATE TABLE core.staging_product_metrics (
                            id SERIAL PRIMARY KEY,
                            platform VARCHAR(32) NOT NULL,
                            shop_id VARCHAR(64) NOT NULL,
                            product_sku VARCHAR(64) NOT NULL,
                            metric_data JSONB,
                            processed BOOLEAN DEFAULT FALSE,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
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
