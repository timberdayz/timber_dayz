from pathlib import Path
import os
import subprocess
import sys
import time

import psycopg2


def test_collection_config_shop_scope_migration_moves_legacy_public_table_into_core():
    admin_conn = psycopg2.connect(
        host="127.0.0.1",
        port=15432,
        user="erp_user",
        password="erp_pass_2025",
        dbname="postgres",
    )
    admin_conn.autocommit = True
    rehearsal_db = f"xihong_erp_collection_scope_test_{int(time.time())}"

    try:
        with admin_conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {rehearsal_db}")
            cur.execute(f"CREATE DATABASE {rehearsal_db}")
            cur.execute(
                f"ALTER DATABASE {rehearsal_db} SET search_path TO '\"$user\"', public"
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
                    cur.execute("CREATE SCHEMA IF NOT EXISTS core")
                    cur.execute(
                        """
                        CREATE TABLE core.alembic_version (
                            version_num VARCHAR(64) NOT NULL PRIMARY KEY
                        )
                        """
                    )
                    cur.execute(
                        "INSERT INTO core.alembic_version(version_num) VALUES (%s)",
                        ("20260403_sync_progress_submitted",),
                    )
                    cur.execute(
                        """
                        CREATE TABLE core.main_accounts (
                            id SERIAL PRIMARY KEY,
                            platform VARCHAR(50) NOT NULL,
                            main_account_id VARCHAR(100) NOT NULL UNIQUE,
                            username VARCHAR(200) NOT NULL,
                            password_encrypted TEXT NOT NULL,
                            enabled BOOLEAN NOT NULL DEFAULT TRUE
                        )
                        """
                    )
                    cur.execute(
                        """
                        INSERT INTO core.main_accounts (
                            platform,
                            main_account_id,
                            username,
                            password_encrypted,
                            enabled
                        ) VALUES (%s, %s, %s, %s, %s)
                        """,
                        ("shopee", "main-a", "main-a-user", "enc", True),
                    )
                    cur.execute(
                        """
                        CREATE TABLE core.shop_accounts (
                            id SERIAL PRIMARY KEY,
                            platform VARCHAR(50) NOT NULL,
                            shop_account_id VARCHAR(100) NOT NULL UNIQUE,
                            main_account_id VARCHAR(100) NOT NULL,
                            store_name VARCHAR(200) NOT NULL,
                            enabled BOOLEAN NOT NULL DEFAULT TRUE,
                            CONSTRAINT fk_shop_accounts_main_account
                                FOREIGN KEY (main_account_id)
                                REFERENCES core.main_accounts(main_account_id)
                                ON DELETE CASCADE
                        )
                        """
                    )
                    cur.execute(
                        """
                        INSERT INTO core.shop_accounts (
                            platform,
                            shop_account_id,
                            main_account_id,
                            store_name,
                            enabled
                        ) VALUES (%s, %s, %s, %s, %s)
                        """,
                        ("shopee", "shop-a-1", "main-a", "Shop A 1", True),
                    )
                    cur.execute(
                        """
                        CREATE TABLE public.collection_configs (
                            id SERIAL PRIMARY KEY,
                            name VARCHAR(100) NOT NULL,
                            platform VARCHAR(50) NOT NULL,
                            account_ids JSON,
                            data_domains JSON,
                            sub_domains JSON,
                            granularity VARCHAR(50),
                            date_range_type VARCHAR(50),
                            custom_date_start TIMESTAMP NULL,
                            custom_date_end TIMESTAMP NULL,
                            schedule_enabled BOOLEAN DEFAULT FALSE NOT NULL,
                            schedule_cron VARCHAR(100),
                            retry_count INTEGER DEFAULT 3 NOT NULL,
                            is_active BOOLEAN DEFAULT TRUE NOT NULL,
                            execution_mode VARCHAR(20) DEFAULT 'headless' NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                            CONSTRAINT uq_collection_configs_name_platform UNIQUE (name, platform)
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
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "alembic.ini",
                "upgrade",
                "20260406_collection_config_main_account_scope",
            ],
            cwd=str(Path.cwd()),
            env=env,
            capture_output=True,
            text=True,
            timeout=240,
        )

        assert (
            result.returncode == 0
        ), f"alembic upgrade failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"

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
                        SELECT table_schema, table_name
                        FROM information_schema.tables
                        WHERE table_name IN ('collection_configs', 'collection_config_shop_scopes')
                        ORDER BY table_schema, table_name
                        """
                    )
                    tables = cur.fetchall()
        finally:
            conn.close()

        assert tables == [
            ("core", "collection_config_shop_scopes"),
            ("core", "collection_configs"),
        ]
    finally:
        with admin_conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {rehearsal_db}")
        admin_conn.close()
