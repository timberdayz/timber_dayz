from pathlib import Path
import os
import re
import subprocess
import sys
import time
from urllib.parse import quote, urlparse

import psycopg2
import pytest

from backend.utils.project_env import isolated_database_url


CURRENT_REVISION = "20260415_c_class_employee_metrics_cleanup"


def _candidate_databases():
    """能 CREATE DATABASE 的 PostgreSQL 候选地址。

    优先用**测试护栏的一次性隔离容器**（``XIHONG_TEST_DATABASE_URL``）——
    这才符合「测试绝不碰真实业务库」的家规；
    容器用不了时退回本地开发库（127.0.0.1:15432）；
    两者都连不上就跳过，别把没有本地库的 CI 拖红。
    """
    candidates = []
    guard_url = isolated_database_url()
    if guard_url:
        parsed = urlparse(guard_url)
        candidates.append(
            (
                parsed.hostname or "localhost",
                parsed.port or 5432,
                parsed.username or "",
                parsed.password or "",
            )
        )
    candidates.append(("127.0.0.1", 15432, "erp_user", "erp_pass_2025"))
    return candidates


def _connect_admin():
    """连上能 CREATE DATABASE 的 PostgreSQL；都不行就跳过。"""
    last_error = None
    for host, port, user, password in _candidate_databases():
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                dbname="postgres",
                connect_timeout=3,
            )
            conn.autocommit = True
            return conn, (host, port, user, password)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    pytest.skip(
        f"没有可用的 PostgreSQL 演练环境（隔离容器与本地库都连不上）：{last_error}"
    )


def _find_field_mapping_template_parse_rules_migration() -> Path:
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*field_parse_rules*.py"))
    assert matches, "expected a field-parse-rules migration in migrations/versions"
    return matches[-1]


def _field_mapping_template_parse_rules_revision() -> str:
    source = _find_field_mapping_template_parse_rules_migration().read_text(
        encoding="utf-8"
    )
    match = re.search(r'^revision\s*=\s*"([^"]+)"', source, re.MULTILINE)
    assert match, "expected revision identifier in parse-rules migration source"
    return match.group(1)


def test_field_mapping_template_parse_rules_migration_exists():
    _find_field_mapping_template_parse_rules_migration()


def _schema_package_source() -> str:
    """schema 包源文本 —— 聚合器 `schema.py` + `schema_parts/*.py` 分片一起读。

    2026-10-31 实测修正：schema 拆分成 `modules/core/db/schema_parts/` 后，
    列定义已迁到分片文件（`field_parse_rules = Column(JSONB, ...)` 在
    `schema_parts/data_platform.py`），聚合器 `modules/core/db/schema.py`
    里已无任何字面量（`Column(` / `mapped_column(` 计数均为 0）。
    只读聚合器会误判「列不存在」→ 断言过期。读整个包则与拆分方式解耦。
    """
    parts = [Path("modules/core/db/schema.py")]
    parts += sorted(Path("modules/core/db/schema_parts").glob("*.py"))
    return "\n".join(
        p.read_text(encoding="utf-8", errors="replace") for p in parts if p.exists()
    )


def test_field_mapping_template_schema_defines_parse_rules_column():
    source = _schema_package_source()

    assert "field_parse_rules = Column(JSONB" in source
    assert "field_parse_rules" in source


def test_field_mapping_template_parse_rules_migration_adds_jsonb_column():
    admin_conn, (host, port, user, password) = _connect_admin()
    rehearsal_db = f"xihong_erp_template_parse_rules_{int(time.time())}"

    try:
        with admin_conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {rehearsal_db}")
            cur.execute(f"CREATE DATABASE {rehearsal_db}")

        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
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
        env["DATABASE_URL"] = (
            f"postgresql://{quote(user)}:{quote(password)}@{host}:{port}/{rehearsal_db}"
        )
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

        assert (
            result.returncode == 0
        ), f"alembic upgrade failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"

        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
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
