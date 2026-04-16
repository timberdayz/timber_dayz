from pathlib import Path
import os
import re
import subprocess
import sys
import time

import psycopg2


CURRENT_REVISION = "20260415_c_class_employee_metrics_cleanup"


def _find_field_mapping_template_parse_rules_migration() -> Path:
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*field_parse_rules*.py"))
    assert matches, "expected a field-parse-rules migration in migrations/versions"
    return matches[-1]


def _field_mapping_template_parse_rules_revision() -> str:
    source = _find_field_mapping_template_parse_rules_migration().read_text(encoding="utf-8")
    match = re.search(r'^revision\s*=\s*"([^"]+)"', source, re.MULTILINE)
    assert match, "expected revision identifier in parse-rules migration source"
    return match.group(1)


def test_field_mapping_template_parse_rules_migration_exists():
    _find_field_mapping_template_parse_rules_migration()


def test_field_mapping_template_schema_defines_parse_rules_column():
    source = Path("modules/core/db/schema.py").read_text(encoding="utf-8")

    assert "field_parse_rules = Column(JSONB" in source
    assert "field_parse_rules" in source


def test_field_mapping_template_parse_rules_migration_adds_jsonb_column():
    admin_conn = psycopg2.connect(
        host="127.0.0.1",
        port=15432,
        user="erp_user",
        password="erp_pass_2025",
        dbname="postgres",
    )
    admin_conn.autocommit = True
    rehearsal_db = f"xihong_erp_template_parse_rules_{int(time.time())}"

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
                            sub_domain VARCHAR(64),
                            header_row INTEGER NOT NULL DEFAULT 0,
                            sheet_name VARCHAR(128),
                            encoding VARCHAR(32) NOT NULL DEFAULT 'utf-8',
                            header_columns JSONB,
                            deduplication_fields JSONB,
                            template_name VARCHAR(256),
                            version INTEGER NOT NULL,
                            status VARCHAR(32),
                            field_count INTEGER,
                            usage_count INTEGER,
                            success_rate FLOAT,
                            created_by VARCHAR(64),
                            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                            updated_by VARCHAR(64),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                            notes TEXT
                        )
                        """
                    )
        finally:
            conn.close()

        env = os.environ.copy()
        env["DATABASE_URL"] = f"postgresql://erp_user:erp_pass_2025@127.0.0.1:15432/{rehearsal_db}"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "alembic.ini",
                "upgrade",
                _field_mapping_template_parse_rules_revision(),
            ],
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
                        SELECT data_type, udt_name
                        FROM information_schema.columns
                        WHERE table_schema = 'core'
                          AND table_name = 'field_mapping_templates'
                          AND column_name = 'field_parse_rules'
                        """
                    )
                    row = cur.fetchone()
                    assert row is not None
                    assert row[1] == "jsonb"
        finally:
            conn.close()
    finally:
        with admin_conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {rehearsal_db}")
        admin_conn.close()
