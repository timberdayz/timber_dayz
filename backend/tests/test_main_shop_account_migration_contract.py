from pathlib import Path
import os
import subprocess
import sys
import time

import psycopg2
from alembic.config import Config
from alembic.script import ScriptDirectory


def _find_main_shop_account_migration() -> Path:
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*main*shop*account*domain*chain*.py"))
    assert matches, "expected a main/shop account domain-chain migration in migrations/versions"
    return matches[-1]


def test_main_shop_account_migration_exists():
    _find_main_shop_account_migration()


def test_main_shop_account_migration_mentions_new_tables_and_old_source_table():
    migration_path = _find_main_shop_account_migration()
    source = migration_path.read_text(encoding="utf-8")

    assert "main_accounts" in source
    assert "shop_accounts" in source
    assert "shop_account_aliases" in source
    assert "shop_account_capabilities" in source
    assert "platform_shop_discoveries" in source
    assert "platform_accounts" in source
    assert 'unique=True' in source or 'sa.UniqueConstraint("main_account_id"' in source
    assert 'sa.UniqueConstraint("shop_account_id"' in source


def test_main_shop_account_migration_has_single_head():
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    assert len(script.get_heads()) == 1


def test_main_shop_account_migration_applies_changes_to_postgres_rehearsal_db():
    admin_conn = psycopg2.connect(
        host="127.0.0.1",
        port=15432,
        user="erp_user",
        password="erp_pass_2025",
        dbname="postgres",
    )
    admin_conn.autocommit = True
    rehearsal_db = f"xihong_erp_rehearsal_test_{int(time.time())}"

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
                        ("20260401_public_alembic_archive",),
                    )
                    cur.execute(
                        """
                        CREATE TABLE core.platform_accounts (
                            id SERIAL PRIMARY KEY,
                            platform VARCHAR(50) NOT NULL,
                            account_id VARCHAR(100) NOT NULL,
                            parent_account VARCHAR(100),
                            username VARCHAR(200) NOT NULL,
                            password_encrypted TEXT NOT NULL,
                            login_url TEXT,
                            enabled BOOLEAN NOT NULL DEFAULT TRUE,
                            notes TEXT,
                            extra_config JSONB,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                            created_by VARCHAR(100),
                            updated_by VARCHAR(100),
                            store_name VARCHAR(200) NOT NULL,
                            shop_id VARCHAR(256),
                            shop_region VARCHAR(50),
                            shop_type VARCHAR(50),
                            proxy_required BOOLEAN DEFAULT FALSE,
                            currency VARCHAR(16),
                            region VARCHAR(50),
                            email VARCHAR(200),
                            phone VARCHAR(50),
                            account_alias VARCHAR(256),
                            capabilities JSONB
                        )
                        """
                    )
                    cur.execute(
                        """
                        INSERT INTO core.platform_accounts (
                            platform,
                            account_id,
                            parent_account,
                            username,
                            password_encrypted,
                            store_name,
                            account_alias,
                            capabilities
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                        """,
                        (
                            "shopee",
                            "shop_alpha",
                            "main_alpha",
                            "alpha_user",
                            "enc",
                            "Alpha Store",
                            "Alpha Alias",
                            '{"orders": true, "products": true}',
                        ),
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
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = 'core'
                          AND table_name IN (
                              'main_accounts',
                              'shop_accounts',
                              'shop_account_aliases',
                              'shop_account_capabilities',
                              'platform_shop_discoveries'
                          )
                        ORDER BY table_name
                        """
                    )
                    table_names = [row[0] for row in cur.fetchall()]
                    cur.execute("SELECT version_num FROM core.alembic_version")
                    revision = cur.fetchone()[0]

            assert table_names == [
                "main_accounts",
                "platform_shop_discoveries",
                "shop_account_aliases",
                "shop_account_capabilities",
                "shop_accounts",
            ]
            assert revision == "20260402_main_shop_accounts"
        finally:
            conn.close()
    finally:
        with admin_conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {rehearsal_db}")
        admin_conn.close()
