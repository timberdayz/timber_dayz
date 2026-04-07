from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

from backend.utils.config import get_settings


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MERGE_REVISION = "20260328_task_center_merge"


def _admin_url(database_url: str) -> URL:
    url = make_url(database_url)
    return url.set(database="postgres")


def _temp_db_name() -> str:
    return f"schema_cleanup_rehearsal_{uuid.uuid4().hex[:10]}"


def _run_command(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        args,
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(args)}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed


def _table_exists(engine, schema: str, table_name: str) -> bool:
    with engine.connect() as conn:
        value = conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = :schema_name
                  AND table_name = :table_name
                LIMIT 1
                """
            ),
            {"schema_name": schema, "table_name": table_name},
        ).scalar()
    return value is not None


def _create_temp_database(admin_engine, database_name: str) -> None:
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{database_name}"'))


def _drop_temp_database(admin_engine, database_name: str) -> None:
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'))


def _seed_public_target_breakdown_duplicate(temp_engine) -> None:
    with temp_engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS a_class"))
        conn.execute(text("DROP TABLE IF EXISTS public.target_breakdown"))
        conn.execute(
            text(
                """
                CREATE TABLE public.target_breakdown
                (LIKE a_class.target_breakdown INCLUDING ALL)
                """
            )
        )


def _ensure_public_dim_shops_duplicate(temp_engine) -> None:
    with temp_engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS core"))
        public_exists = conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'dim_shops'
                LIMIT 1
                """
            )
        ).scalar()
        core_exists = conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'core' AND table_name = 'dim_shops'
                LIMIT 1
                """
            )
        ).scalar()
        if core_exists and not public_exists:
            conn.execute(
                text(
                    """
                    CREATE TABLE public.dim_shops
                    (LIKE core.dim_shops INCLUDING ALL)
                    """
                )
            )


def _verify_schema_completeness(database_url: str) -> dict[str, object]:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    result = _run_command(
        [
            "python",
            "-c",
            (
                "import json; "
                "from backend.models.database import verify_schema_completeness; "
                "print(json.dumps(verify_schema_completeness()))"
            ),
        ],
        env=env,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def run_wave1_rehearsal() -> dict[str, object]:
    settings = get_settings()
    base_url = make_url(settings.DATABASE_URL)
    admin_engine = create_engine(
        _admin_url(settings.DATABASE_URL),
        isolation_level="AUTOCOMMIT",
        future=True,
    )

    database_name = _temp_db_name()
    temp_url = base_url.set(database=database_name).render_as_string(hide_password=False)
    env = os.environ.copy()
    env["DATABASE_URL"] = temp_url

    try:
        _create_temp_database(admin_engine, database_name)

        _run_command(["alembic", "upgrade", MERGE_REVISION], env=env)

        temp_engine = create_engine(temp_url, future=True)
        try:
            _seed_public_target_breakdown_duplicate(temp_engine)
            public_before = _table_exists(temp_engine, "public", "target_breakdown")
        finally:
            temp_engine.dispose()

        _run_command(["alembic", "upgrade", "head"], env=env)

        temp_engine = create_engine(temp_url, future=True)
        try:
            public_after = _table_exists(temp_engine, "public", "target_breakdown")
            archive_after = _table_exists(temp_engine, "public", "target_breakdown__archive_wave1")
            a_class_after = _table_exists(temp_engine, "a_class", "target_breakdown")
        finally:
            temp_engine.dispose()

        completeness = _verify_schema_completeness(temp_url)
        completeness.update(
            {
                "database_name": database_name,
                "public_target_breakdown_exists_before": public_before,
                "public_target_breakdown_exists_after": public_after,
                "archive_table_exists_after": archive_after,
                "a_class_target_breakdown_exists_after": a_class_after,
            }
        )
        return completeness
    finally:
        _drop_temp_database(admin_engine, database_name)
        admin_engine.dispose()


def run_dim_shops_public_retirement_rehearsal() -> dict[str, object]:
    settings = get_settings()
    base_url = make_url(settings.DATABASE_URL)
    admin_engine = create_engine(
        _admin_url(settings.DATABASE_URL),
        isolation_level="AUTOCOMMIT",
        future=True,
    )

    database_name = _temp_db_name()
    temp_url = base_url.set(database=database_name).render_as_string(hide_password=False)
    env = os.environ.copy()
    env["DATABASE_URL"] = temp_url

    try:
        _create_temp_database(admin_engine, database_name)

        _run_command(["alembic", "upgrade", "20260328_dim_shops_core"], env=env)

        temp_engine = create_engine(temp_url, future=True)
        try:
            _ensure_public_dim_shops_duplicate(temp_engine)
            public_before = _table_exists(temp_engine, "public", "dim_shops")
            core_before = _table_exists(temp_engine, "core", "dim_shops")
        finally:
            temp_engine.dispose()

        _run_command(["alembic", "upgrade", "head"], env=env)

        temp_engine = create_engine(temp_url, future=True)
        try:
            public_after = _table_exists(temp_engine, "public", "dim_shops")
            archive_after = _table_exists(temp_engine, "public", "dim_shops__archive_retired")
            core_after = _table_exists(temp_engine, "core", "dim_shops")
        finally:
            temp_engine.dispose()

        completeness = _verify_schema_completeness(temp_url)
        completeness.update(
            {
                "database_name": database_name,
                "public_dim_shops_exists_before": public_before,
                "core_dim_shops_exists_before": core_before,
                "public_dim_shops_exists_after": public_after,
                "archive_dim_shops_exists_after": archive_after,
                "core_dim_shops_exists_after": core_after,
            }
        )
        return completeness
    finally:
        _drop_temp_database(admin_engine, database_name)
        admin_engine.dispose()
