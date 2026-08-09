"""Real PostgreSQL contracts for the fail-closed current-schema migration entrypoint."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

import scripts.run_current_schema_migrations as migration_runner


ROOT = Path(__file__).resolve().parents[1]
CURRENT_BASELINE_REVISION = "current_schema_20260805"
CURRENT_HEAD_REVISION = "current_schema_20260808_operation_performance_workbench"
LEGACY_REVISION = "20260805_payroll_backfill_audit"


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    result = subprocess.run(
        ["docker", "info"], capture_output=True, text=True, check=False
    )
    return result.returncode == 0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _wait_for_postgres(container_id: str) -> None:
    for _ in range(30):
        result = subprocess.run(
            ["docker", "exec", container_id, "pg_isready", "-U", "current_test"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return
        time.sleep(1)
    raise RuntimeError("temporary PostgreSQL container did not become ready")


def test_current_wrapper_rejects_nonempty_database_without_mutation_then_bootstraps_fresh():
    if not _docker_available():
        pytest.skip("requires a reachable Docker daemon and PostgreSQL 15 image")

    port = _free_port()
    started = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "-e",
            "POSTGRES_USER=current_test",
            "-e",
            "POSTGRES_PASSWORD=current_test",
            "-e",
            "POSTGRES_DB=current_test",
            "-p",
            f"127.0.0.1:{port}:5432",
            "postgres:15",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    container_id = started.stdout.strip()
    database_url = f"postgresql://current_test:current_test@127.0.0.1:{port}/current_test"
    try:
        _wait_for_postgres(container_id)
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE public.legacy_probe (id integer primary key)"))

        rejected = subprocess.run(
            [sys.executable, "scripts/run_current_schema_migrations.py"],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": database_url},
            capture_output=True,
            text=True,
            check=False,
        )
        assert rejected.returncode == 2
        assert "not an approved legacy source" in rejected.stderr
        assert inspect(engine).has_table("legacy_probe", schema="public")
        assert not inspect(engine).has_table("current_schema_alembic_version", schema="public")

        with engine.begin() as connection:
            connection.execute(text("CREATE SCHEMA core"))
            connection.execute(
                text(
                    "CREATE TABLE core.alembic_version "
                    "(version_num varchar(64) NOT NULL PRIMARY KEY)"
                )
            )
            connection.execute(
                text("INSERT INTO core.alembic_version (version_num) VALUES ('unknown')")
            )

        unknown_revision = subprocess.run(
            [sys.executable, "scripts/run_current_schema_migrations.py"],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": database_url},
            capture_output=True,
            text=True,
            check=False,
        )
        assert unknown_revision.returncode == 2
        assert "not an approved legacy source" in unknown_revision.stderr
        assert inspect(engine).has_table("legacy_probe", schema="public")
        assert not inspect(engine).has_table("current_schema_alembic_version", schema="public")

        with engine.begin() as connection:
            connection.execute(text("DELETE FROM core.alembic_version"))
            connection.execute(
                text(
                    "INSERT INTO core.alembic_version (version_num) "
                    "VALUES ('20260805_payroll_backfill_audit')"
                )
            )

        mismatched_fingerprint = subprocess.run(
            [sys.executable, "scripts/run_current_schema_migrations.py"],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": database_url},
            capture_output=True,
            text=True,
            check=False,
        )
        assert mismatched_fingerprint.returncode == 2
        assert "fingerprint is not approved" in mismatched_fingerprint.stderr
        assert inspect(engine).has_table("legacy_probe", schema="public")
        assert not inspect(engine).has_table("current_schema_alembic_version", schema="public")

        with engine.begin() as connection:
            connection.execute(text("DROP TABLE core.alembic_version"))
            connection.execute(text("DROP SCHEMA core"))
            connection.execute(text("DROP TABLE public.legacy_probe"))

        bootstrapped = subprocess.run(
            [sys.executable, "scripts/run_current_schema_migrations.py"],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": database_url},
            capture_output=True,
            text=True,
            check=False,
        )
        assert bootstrapped.returncode == 0, bootstrapped.stderr
        assert inspect(engine).has_table("current_schema_alembic_version", schema="public")
        assert len(inspect(engine).get_table_names(schema="a_class")) > 0
    finally:
        subprocess.run(["docker", "stop", "-t", "1", container_id], check=False)


def test_approved_legacy_adoption_preserves_business_data_and_runs_current_increment(
    tmp_path, monkeypatch
):
    """A supported production-shaped database stamps only the static baseline."""
    if not _docker_available():
        pytest.skip("requires a reachable Docker daemon and PostgreSQL 15 image")

    port = _free_port()
    started = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "-e",
            "POSTGRES_USER=current_test",
            "-e",
            "POSTGRES_PASSWORD=current_test",
            "-e",
            "POSTGRES_DB=current_test",
            "-p",
            f"127.0.0.1:{port}:5432",
            "postgres:15",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    container_id = started.stdout.strip()
    database_url = f"postgresql://current_test:current_test@127.0.0.1:{port}/current_test"
    try:
        _wait_for_postgres(container_id)
        baseline = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "alembic-current.ini",
                "upgrade",
                CURRENT_BASELINE_REVISION,
            ],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": database_url},
            capture_output=True,
            text=True,
            check=False,
        )
        assert baseline.returncode == 0, baseline.stderr

        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO a_class.employees (employee_code, name) "
                    "VALUES ('MIGRATION-KEEP', 'Migration Keep')"
                )
            )
            connection.execute(
                text("DROP TABLE public.current_schema_alembic_version")
            )
            connection.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS core.alembic_version "
                    "(version_num varchar(64) NOT NULL PRIMARY KEY)"
                )
            )
            connection.execute(text("DELETE FROM core.alembic_version"))
            connection.execute(
                text("INSERT INTO core.alembic_version (version_num) VALUES (:revision)"),
                {"revision": LEGACY_REVISION},
            )

        with engine.connect() as connection:
            fingerprint = migration_runner.schema_fingerprint(connection)
        policy_path = tmp_path / "support_policy.json"
        policy_path.write_text(
            '{"approved_legacy_sources":[{"legacy_revision":"'
            + LEGACY_REVISION
            + '","schema_fingerprint":"'
            + fingerprint
            + '","baseline_revision":"'
            + CURRENT_BASELINE_REVISION
            + '"}]}',
            encoding="utf-8",
        )
        monkeypatch.setattr(migration_runner, "SUPPORT_POLICY_PATH", policy_path)

        assert (
            migration_runner.run_current_schema_migrations(
                database_url,
                expected_source_revision=None,
                expected_source_fingerprint=None,
            )
            == "stamp"
        )

        inspector = inspect(engine)
        assert inspector.has_table("operation_metric_catalog", schema="a_class")
        with engine.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT name FROM a_class.employees "
                    "WHERE employee_code = 'MIGRATION-KEEP'"
                )
            ).scalar_one() == "Migration Keep"
            assert connection.execute(
                text("SELECT version_num FROM public.current_schema_alembic_version")
            ).scalar_one() == CURRENT_HEAD_REVISION
            assert connection.execute(
                text("SELECT version_num FROM core.alembic_version")
            ).scalar_one() == LEGACY_REVISION

        assert (
            migration_runner.run_current_schema_migrations(
                database_url,
                expected_source_revision=None,
                expected_source_fingerprint=None,
            )
            == "upgrade"
        )
        with engine.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT name FROM a_class.employees "
                    "WHERE employee_code = 'MIGRATION-KEEP'"
                )
            ).scalar_one() == "Migration Keep"
    finally:
        subprocess.run(["docker", "stop", "-t", "1", container_id], check=False)


def test_legacy_adoption_rejects_duplicate_operation_shop_overrides_before_writing(
    tmp_path, monkeypatch
):
    if not _docker_available():
        pytest.skip("requires a reachable Docker daemon and PostgreSQL 15 image")

    port = _free_port()
    started = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "-e",
            "POSTGRES_USER=current_test",
            "-e",
            "POSTGRES_PASSWORD=current_test",
            "-e",
            "POSTGRES_DB=current_test",
            "-p",
            f"127.0.0.1:{port}:5432",
            "postgres:15",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    container_id = started.stdout.strip()
    database_url = f"postgresql://current_test:current_test@127.0.0.1:{port}/current_test"
    try:
        _wait_for_postgres(container_id)
        baseline = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "alembic-current.ini",
                "upgrade",
                CURRENT_BASELINE_REVISION,
            ],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": database_url},
            capture_output=True,
            text=True,
            check=False,
        )
        assert baseline.returncode == 0, baseline.stderr

        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO core.dim_platforms (platform_code, name, is_active) "
                    "VALUES ('platform', 'Platform', true)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO core.dim_shops (platform_code, shop_id, shop_name) "
                    "VALUES ('platform', 'shop', 'Shop')"
                )
            )
            target_id = connection.execute(
                text(
                    "INSERT INTO a_class.sales_targets "
                    "(target_name, target_type, period_start, period_end, scope_type, "
                    "metric_code, metric_direction, target_value, max_score) "
                    "VALUES ('Legacy operation', 'operation', '2026-07-01', '2026-07-31', "
                    "'shop', 'legacy_metric', 'higher_better', 1, 10) RETURNING id"
                )
            ).scalar_one()
            for achieved_value in (1, 2):
                connection.execute(
                    text(
                        "INSERT INTO a_class.target_breakdown "
                        "(target_id, breakdown_type, platform_code, shop_id, "
                        "period_start, period_end, target_amount, target_quantity, "
                        "achieved_amount, achieved_quantity, achievement_rate, achieved_value) "
                        "VALUES (:target_id, 'shop', 'platform', 'shop', "
                        "'2026-07-01', '2026-07-31', 1, 0, 0, 0, 0, :achieved_value)"
                    ),
                    {"target_id": target_id, "achieved_value": achieved_value},
                )
            connection.execute(text("DROP TABLE public.current_schema_alembic_version"))
            connection.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS core.alembic_version "
                    "(version_num varchar(64) NOT NULL PRIMARY KEY)"
                )
            )
            connection.execute(text("DELETE FROM core.alembic_version"))
            connection.execute(
                text("INSERT INTO core.alembic_version (version_num) VALUES (:revision)"),
                {"revision": LEGACY_REVISION},
            )

        with engine.connect() as connection:
            fingerprint = migration_runner.schema_fingerprint(connection)
        policy_path = tmp_path / "support_policy.json"
        policy_path.write_text(
            '{"approved_legacy_sources":[{"legacy_revision":"'
            + LEGACY_REVISION
            + '","schema_fingerprint":"'
            + fingerprint
            + '","baseline_revision":"'
            + CURRENT_BASELINE_REVISION
            + '"}]}',
            encoding="utf-8",
        )
        monkeypatch.setattr(migration_runner, "SUPPORT_POLICY_PATH", policy_path)

        with pytest.raises(migration_runner.MigrationSafetyError, match="duplicate operation"):
            migration_runner.run_current_schema_migrations(
                database_url,
                expected_source_revision=None,
                expected_source_fingerprint=None,
            )

        inspector = inspect(engine)
        assert not inspector.has_table("current_schema_alembic_version", schema="public")
        with engine.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT count(*) FROM a_class.target_breakdown "
                    "WHERE target_id = :target_id"
                ),
                {"target_id": target_id},
            ).scalar_one() == 2
    finally:
        subprocess.run(["docker", "stop", "-t", "1", container_id], check=False)
