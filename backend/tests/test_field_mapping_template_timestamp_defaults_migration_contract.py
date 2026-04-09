from pathlib import Path
import os
import subprocess
import sys
import time

import psycopg2


CURRENT_REVISION = "20260407_follow_investment_profit_basis"


def _find_field_mapping_template_timestamp_migration() -> Path:
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*field_mapping_template*timestamp*.py"))
    assert matches, "expected a field-mapping-template timestamp repair migration in migrations/versions"
    return matches[-1]


def test_field_mapping_template_timestamp_migration_exists():
    _find_field_mapping_template_timestamp_migration()


def test_field_mapping_template_timestamp_migration_mentions_timestamp_defaults():
    migration_path = _find_field_mapping_template_timestamp_migration()
    source = migration_path.read_text(encoding="utf-8")

    assert "field_mapping_templates" in source
    assert "created_at" in source
    assert "updated_at" in source
    assert "SET DEFAULT now()" in source or "server_default=sa.text(\"now()\")" in source


def test_field_mapping_template_timestamp_migration_repairs_drifted_postgres_table():
    admin_conn = psycopg2.connect(
        host="127.0.0.1",
        port=15432,
        user="erp_user",
        password="erp_pass_2025",
        dbname="postgres",
    )
    admin_conn.autocommit = True
    rehearsal_db = f"xihong_erp_template_ts_{int(time.time())}"

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
                            version_num VARCHAR(64) NOT NULL PRIMARY KEY
                        )
                        """
                    )
                    cur.execute(
                        "INSERT INTO core.alembic_version(version_num) VALUES (%s)",
                        (CURRENT_REVISION,),
                    )
                    cur.execute(
                        """
                        CREATE TABLE core.field_mapping_templates (
                            id SERIAL PRIMARY KEY,
                            platform VARCHAR(32) NOT NULL,
                            data_domain VARCHAR(64) NOT NULL,
                            granularity VARCHAR(32),
                            account VARCHAR(128),
                            template_name VARCHAR(256),
                            version INTEGER NOT NULL,
                            status VARCHAR(32),
                            field_count INTEGER,
                            usage_count INTEGER,
                            success_rate FLOAT,
                            created_by VARCHAR(64),
                            created_at TIMESTAMP NOT NULL,
                            updated_by VARCHAR(64),
                            updated_at TIMESTAMP,
                            notes TEXT,
                            sub_domain VARCHAR(64),
                            header_row INTEGER NOT NULL DEFAULT 0,
                            sheet_name VARCHAR(128),
                            encoding VARCHAR(32) NOT NULL DEFAULT 'utf-8',
                            header_columns JSONB,
                            deduplication_fields JSONB
                        )
                        """
                    )
        finally:
            conn.close()

        env = os.environ.copy()
        env["DATABASE_URL"] = f"postgresql://erp_user:erp_pass_2025@127.0.0.1:15432/{rehearsal_db}"
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
                        SELECT column_name, column_default
                        FROM information_schema.columns
                        WHERE table_schema = 'core'
                          AND table_name = 'field_mapping_templates'
                          AND column_name IN ('created_at', 'updated_at')
                        ORDER BY column_name
                        """
                    )
                    defaults = {row[0]: row[1] for row in cur.fetchall()}

                    assert defaults["created_at"] is not None
                    assert "now()" in defaults["created_at"].lower()
                    assert defaults["updated_at"] is not None
                    assert "now()" in defaults["updated_at"].lower()

                    cur.execute(
                        """
                        INSERT INTO core.field_mapping_templates (
                            platform,
                            data_domain,
                            granularity,
                            account,
                            sub_domain,
                            header_row,
                            sheet_name,
                            encoding,
                            header_columns,
                            deduplication_fields,
                            template_name,
                            version,
                            status,
                            field_count,
                            usage_count,
                            success_rate,
                            created_by,
                            updated_by,
                            notes
                        ) VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s::jsonb, %s::jsonb,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        RETURNING created_at, updated_at
                        """,
                        (
                            "shopee",
                            "orders",
                            "daily",
                            None,
                            None,
                            1,
                            None,
                            "utf-8",
                            "[]",
                            '["order_id"]',
                            "migration_contract_template",
                            1,
                            "published",
                            0,
                            0,
                            0.0,
                            "test",
                            None,
                            "migration smoke test",
                        ),
                    )
                    created_at, updated_at = cur.fetchone()
                    assert created_at is not None
                    assert updated_at is not None
        finally:
            conn.close()
    finally:
        with admin_conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {rehearsal_db}")
        admin_conn.close()
