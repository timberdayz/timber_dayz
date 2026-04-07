from pathlib import Path
import os
import subprocess
import sys
import time

import psycopg2

from tests.db_test_config import admin_connection_kwargs, database_connection_kwargs, database_url


def test_follow_investment_migration_bootstraps_finance_schema():
    admin_conn = psycopg2.connect(
        **admin_connection_kwargs(),
    )
    admin_conn.autocommit = True
    rehearsal_db = f"xihong_erp_follow_investment_test_{int(time.time())}"

    try:
        with admin_conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {rehearsal_db}")
            cur.execute(f"CREATE DATABASE {rehearsal_db}")
            cur.execute(
                f"ALTER DATABASE {rehearsal_db} SET search_path TO '\"$user\"', public"
            )

        conn = psycopg2.connect(
            **database_connection_kwargs(rehearsal_db),
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
                        """
                        INSERT INTO core.alembic_version(version_num)
                        VALUES (%s), (%s)
                        """,
                        (
                            "20260403_add_main_account_name",
                            "20260406_collection_config_main_account_scope",
                        ),
                    )
                    cur.execute(
                        """
                        CREATE TABLE core.dim_fiscal_calendar (
                            period_code VARCHAR(16) PRIMARY KEY
                        )
                        """
                    )
                    cur.execute(
                        """
                        CREATE TABLE core.dim_users (
                            user_id BIGINT PRIMARY KEY
                        )
                        """
                    )
                    cur.execute(
                        "INSERT INTO core.dim_fiscal_calendar(period_code) VALUES ('2026-04')"
                    )
                    cur.execute("INSERT INTO core.dim_users(user_id) VALUES (1)")
        finally:
            conn.close()

        env = os.environ.copy()
        env["DATABASE_URL"] = database_url(rehearsal_db)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "alembic.ini",
                "upgrade",
                "20260407_follow_investment_profit_basis",
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
            **database_connection_kwargs(rehearsal_db),
        )
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT table_schema, table_name
                        FROM information_schema.tables
                        WHERE table_schema = 'finance'
                          AND table_name IN (
                              'shop_profit_basis',
                              'follow_investments',
                              'follow_investment_settlements',
                              'follow_investment_details'
                          )
                        ORDER BY table_name
                        """
                    )
                    tables = cur.fetchall()
        finally:
            conn.close()

        assert tables == [
            ("finance", "follow_investment_details"),
            ("finance", "follow_investment_settlements"),
            ("finance", "follow_investments"),
            ("finance", "shop_profit_basis"),
        ]
    finally:
        with admin_conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {rehearsal_db}")
        admin_conn.close()
