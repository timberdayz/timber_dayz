"""Real PostgreSQL contracts for the fail-closed current-schema migration entrypoint."""

from __future__ import annotations

import os
import json
import hashlib
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
CURRENT_HEAD_REVISION = "current_schema_20260817_operation_performance_monthly_scope"
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
            time.sleep(1)
            return
        time.sleep(1)
    raise RuntimeError("temporary PostgreSQL container did not become ready")


def _write_approved_policy(tmp_path: Path, fingerprint: str) -> Path:
    manifest_path = tmp_path / "approved-manifest.json"
    manifest = {
        "manifest_version": 1,
        "legacy_revision": LEGACY_REVISION,
        "baseline_revision": CURRENT_BASELINE_REVISION,
        "schema_fingerprint": fingerprint,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    policy_path = tmp_path / "support_policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "approved_legacy_sources": [
                    {
                        "legacy_revision": LEGACY_REVISION,
                        "schema_fingerprint": fingerprint,
                        "baseline_revision": CURRENT_BASELINE_REVISION,
                        "manifest_version": 1,
                        "manifest_path": str(manifest_path),
                        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                        "approval_note": "temporary PostgreSQL integration fixture",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return policy_path


def test_migration_advisory_lock_rejects_a_second_writer_without_ddl():
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
        with migration_runner.migration_advisory_lock(database_url):
            with pytest.raises(migration_runner.MigrationSafetyError, match="lock is already held"):
                with migration_runner.migration_advisory_lock(database_url):
                    pass
        engine = create_engine(database_url)
        assert not inspect(engine).get_table_names(schema="public")
    finally:
        subprocess.run(["docker", "stop", "-t", "1", container_id], check=False)


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
    database_url = (
        f"postgresql://current_test:current_test@127.0.0.1:{port}/current_test"
    )
    try:
        _wait_for_postgres(container_id)
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text("CREATE TABLE public.legacy_probe (id integer primary key)")
            )

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
        assert not inspect(engine).has_table(
            "current_schema_alembic_version", schema="public"
        )

        with engine.begin() as connection:
            connection.execute(text("CREATE SCHEMA core"))
            connection.execute(
                text(
                    "CREATE TABLE core.alembic_version "
                    "(version_num varchar(64) NOT NULL PRIMARY KEY)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO core.alembic_version (version_num) VALUES ('unknown')"
                )
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
        assert not inspect(engine).has_table(
            "current_schema_alembic_version", schema="public"
        )

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
        assert not inspect(engine).has_table(
            "current_schema_alembic_version", schema="public"
        )

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
        assert inspect(engine).has_table(
            "current_schema_alembic_version", schema="public"
        )
        assert len(inspect(engine).get_table_names(schema="a_class")) > 0
        assert inspect(engine).has_table(
            "operation_performance_shop_scopes", schema="a_class"
        )
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
    database_url = (
        f"postgresql://current_test:current_test@127.0.0.1:{port}/current_test"
    )
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
            connection.execute(text("DROP TABLE public.current_schema_alembic_version"))
            connection.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS core.alembic_version "
                    "(version_num varchar(64) NOT NULL PRIMARY KEY)"
                )
            )
            connection.execute(text("DELETE FROM core.alembic_version"))
            connection.execute(
                text(
                    "INSERT INTO core.alembic_version (version_num) VALUES (:revision)"
                ),
                {"revision": LEGACY_REVISION},
            )

        with engine.connect() as connection:
            fingerprint = migration_runner.schema_fingerprint(connection)
        policy_path = _write_approved_policy(tmp_path, fingerprint)
        monkeypatch.setattr(migration_runner, "SUPPORT_POLICY_PATH", policy_path)
        monkeypatch.setenv("LOCAL_POSTGRES_CONTAINER", container_id)
        monkeypatch.setenv(migration_runner.LOCAL_BACKUP_GUARD_ENV, "1")

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
            assert (
                connection.execute(
                    text(
                        "SELECT name FROM a_class.employees "
                        "WHERE employee_code = 'MIGRATION-KEEP'"
                    )
                ).scalar_one()
                == "Migration Keep"
            )
            assert (
                connection.execute(
                    text(
                        "SELECT version_num FROM public.current_schema_alembic_version"
                    )
                ).scalar_one()
                == CURRENT_HEAD_REVISION
            )
            assert (
                connection.execute(
                    text("SELECT version_num FROM core.alembic_version")
                ).scalar_one()
                == LEGACY_REVISION
            )

        assert (
            migration_runner.run_current_schema_migrations(
                database_url,
                expected_source_revision=None,
                expected_source_fingerprint=None,
            )
            == "upgrade"
        )
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT name FROM a_class.employees "
                        "WHERE employee_code = 'MIGRATION-KEEP'"
                    )
                ).scalar_one()
                == "Migration Keep"
            )
    finally:
        subprocess.run(["docker", "stop", "-t", "1", container_id], check=False)


def test_legacy_adoption_preserves_duplicate_operation_shop_overrides_and_audits_them(
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
    database_url = (
        f"postgresql://current_test:current_test@127.0.0.1:{port}/current_test"
    )
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
            incomplete_target_id = connection.execute(
                text(
                    "INSERT INTO a_class.sales_targets "
                    "(target_name, target_type, period_start, period_end, scope_type) "
                    "VALUES ('Incomplete legacy operation', 'operation', '2026-07-02', '2026-07-31', NULL) "
                    "RETURNING id"
                )
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO a_class.target_breakdown "
                    "(target_id, breakdown_type, target_amount, target_quantity, "
                    "achieved_amount, achieved_quantity, achievement_rate) "
                    "VALUES (:target_id, 'time', 0, 0, 0, 0, 0)"
                ),
                {"target_id": incomplete_target_id},
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
                text(
                    "INSERT INTO core.alembic_version (version_num) VALUES (:revision)"
                ),
                {"revision": LEGACY_REVISION},
            )

        with engine.connect() as connection:
            fingerprint = migration_runner.schema_fingerprint(connection)
        policy_path = _write_approved_policy(tmp_path, fingerprint)
        monkeypatch.setattr(migration_runner, "SUPPORT_POLICY_PATH", policy_path)
        monkeypatch.setenv("LOCAL_POSTGRES_CONTAINER", container_id)
        monkeypatch.setenv(migration_runner.LOCAL_BACKUP_GUARD_ENV, "1")

        assert (
            migration_runner.run_current_schema_migrations(
                database_url,
                expected_source_revision=None,
                expected_source_fingerprint=None,
            )
            == "stamp"
        )

        inspector = inspect(engine)
        assert inspector.has_table("current_schema_alembic_version", schema="public")
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM a_class.target_breakdown "
                        "WHERE target_id = :target_id"
                    ),
                    {"target_id": target_id},
                ).scalar_one()
                == 2
            )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM a_class.target_breakdown "
                        "WHERE target_id = :target_id "
                        "AND operation_contract_version IS NULL"
                    ),
                    {"target_id": target_id},
                ).scalar_one()
                == 2
            )

        audit = migration_runner.audit_legacy_operation_data(database_url)
        assert audit["legacy_count"] == 2
        assert audit["missing_metric_code"]["count"] == 1
        assert audit["missing_metric_direction"]["count"] == 1
        assert audit["non_calendar_month"]["count"] == 1
        assert audit["missing_shop_scope"]["count"] == 1
        assert audit["incomplete_override"]["count"] == 1
        assert audit["duplicate_override"]["count"] == 2
        assert len(audit["duplicate_override"]["ids"]) == 2
        cli_audit = subprocess.run(
            [
                sys.executable,
                "scripts/run_current_schema_migrations.py",
                "--database-url",
                database_url,
                "--audit-legacy-operation-data",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert cli_audit.returncode == 0, cli_audit.stderr
        assert json.loads(cli_audit.stdout) == audit
    finally:
        subprocess.run(["docker", "stop", "-t", "1", container_id], check=False)


def test_current_operation_contract_rejects_invalid_targets_and_matching_duplicate_overrides():
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
    database_url = (
        f"postgresql://current_test:current_test@127.0.0.1:{port}/current_test"
    )
    try:
        _wait_for_postgres(container_id)
        migrated = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "alembic-current.ini",
                "upgrade",
                "head",
            ],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": database_url},
            capture_output=True,
            text=True,
            check=False,
        )
        assert migrated.returncode == 0, migrated.stderr

        engine = create_engine(database_url)
        with engine.begin() as connection:
            invalid_target_savepoint = connection.begin_nested()
            with pytest.raises(Exception, match="scope_type=shop"):
                connection.execute(
                    text(
                        "INSERT INTO a_class.sales_targets "
                        "(target_name, target_type, period_start, period_end, metric_catalog_version) "
                        "VALUES ('Invalid current', 'operation', '2026-07-01', '2026-07-31', 1)"
                    )
                )
            invalid_target_savepoint.rollback()

            historical_insert_savepoint = connection.begin_nested()
            with pytest.raises(
                Exception, match="historical operation targets are read-only"
            ):
                connection.execute(
                    text(
                        "INSERT INTO a_class.sales_targets "
                        "(target_name, target_type, period_start, period_end) "
                        "VALUES ('Legacy write rejected', 'operation', '2026-07-02', '2026-07-31')"
                    )
                )
            historical_insert_savepoint.rollback()
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

            current_id = connection.execute(
                text(
                    "INSERT INTO a_class.sales_targets "
                    "(target_name, target_type, period_start, period_end, scope_type, metric_code, "
                    "metric_direction, metric_catalog_version) "
                    "VALUES ('Current valid', 'operation', '2026-07-01', '2026-07-31', 'shop', "
                    "'metric', 'higher_better', 1) RETURNING id"
                )
            ).scalar_one()
            invalid_override_savepoint = connection.begin_nested()
            with pytest.raises(Exception, match="only allow shop breakdowns"):
                connection.execute(
                    text(
                        "INSERT INTO a_class.target_breakdown "
                        "(target_id, breakdown_type, operation_contract_version) "
                        "VALUES (:target_id, 'time', 1)"
                    ),
                    {"target_id": current_id},
                )
            invalid_override_savepoint.rollback()
            override_sql = text(
                "INSERT INTO a_class.target_breakdown "
                "(target_id, breakdown_type, platform_code, shop_id, period_start, period_end, "
                "target_amount, target_quantity, achieved_amount, achieved_quantity, achievement_rate, "
                "operation_contract_version) "
                "VALUES (:target_id, 'shop', 'platform', 'shop', '2026-07-01', '2026-07-31', "
                "0, 0, 0, 0, 0, 1)"
            )
            connection.execute(override_sql, {"target_id": current_id})
            duplicate_override_savepoint = connection.begin_nested()
            with pytest.raises(Exception, match="uq_operation_shop_override"):
                connection.execute(override_sql, {"target_id": current_id})
            duplicate_override_savepoint.rollback()

            connection.execute(text("DROP INDEX a_class.uq_operation_shop_override"))
            connection.execute(override_sql, {"target_id": current_id})

        with pytest.raises(
            migration_runner.MigrationSafetyError,
            match="invalid current operation contract data",
        ):
            migration_runner.assert_legacy_adoption_data_is_safe(database_url)

        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE a_class.sales_targets "
                    "DISABLE TRIGGER trg_enforce_operation_target_contract"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO a_class.sales_targets "
                    "(target_name, target_type, period_start, period_end, metric_catalog_version) "
                    "VALUES ('Invalid current preflight', 'operation', '2026-07-01', '2026-07-31', 1)"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE a_class.sales_targets "
                    "ENABLE TRIGGER trg_enforce_operation_target_contract"
                )
            )

        with pytest.raises(
            migration_runner.MigrationSafetyError,
            match="invalid current operation contract data",
        ):
            migration_runner.assert_legacy_adoption_data_is_safe(database_url)

        with pytest.raises(
            migration_runner.MigrationSafetyError,
            match="invalid current operation contract data",
        ):
            migration_runner.run_current_schema_migrations(
                database_url,
                expected_source_revision=None,
                expected_source_fingerprint=None,
            )
    finally:
        subprocess.run(["docker", "stop", "-t", "1", container_id], check=False)


def test_old_20260808_database_upgrades_to_enforce_operation_breakdown_versions():
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
    database_url = (
        f"postgresql://current_test:current_test@127.0.0.1:{port}/current_test"
    )
    try:
        _wait_for_postgres(container_id)
        old_upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "alembic-current.ini",
                "upgrade",
                "current_schema_20260808_operation_performance_workbench",
            ],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": database_url},
            capture_output=True,
            text=True,
            check=False,
        )
        assert old_upgrade.returncode == 0, old_upgrade.stderr

        engine = create_engine(database_url)
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT version_num FROM public.current_schema_alembic_version"
                    )
                ).scalar_one()
                == "current_schema_20260808_operation_performance_workbench"
            )

        with engine.begin() as connection:
            historical_id = connection.execute(
                text(
                    "INSERT INTO a_class.sales_targets "
                    "(target_name, target_type, period_start, period_end) "
                    "VALUES ('Historical versionless', 'operation', '2026-07-01', '2026-07-31') "
                    "RETURNING id"
                )
            ).scalar_one()
            historical_breakdown_id = connection.execute(
                text(
                    "INSERT INTO a_class.target_breakdown "
                    "(target_id, breakdown_type, target_amount, target_quantity, achieved_amount, "
                    "achieved_quantity, achievement_rate) "
                    "VALUES (:target_id, 'time', 0, 0, 0, 0, 0) RETURNING id"
                ),
                {"target_id": historical_id},
            ).scalar_one()

        assert (
            migration_runner.run_current_schema_migrations(
                database_url,
                expected_source_revision=None,
                expected_source_fingerprint=None,
            )
            == "upgrade"
        )

        with engine.begin() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT version_num FROM public.current_schema_alembic_version"
                    )
                ).scalar_one()
                == CURRENT_HEAD_REVISION
            )
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
            current_id = connection.execute(
                text(
                    "INSERT INTO a_class.sales_targets "
                    "(target_name, target_type, period_start, period_end, scope_type, metric_code, "
                    "metric_direction, metric_catalog_version) "
                    "VALUES ('Current versioned', 'operation', '2026-07-01', '2026-07-31', 'shop', "
                    "'metric', 'higher_better', 1) RETURNING id"
                )
            ).scalar_one()
            inherited_breakdown_id = connection.execute(
                text(
                    "INSERT INTO a_class.target_breakdown "
                    "(target_id, breakdown_type, platform_code, shop_id, period_start, period_end, "
                    "target_amount, target_quantity, achieved_amount, achieved_quantity, achievement_rate) "
                    "VALUES (:target_id, 'shop', 'platform', 'shop', '2026-07-01', '2026-07-31', "
                    "0, 0, 0, 0, 0) RETURNING id"
                ),
                {"target_id": current_id},
            ).scalar_one()
            assert (
                connection.execute(
                    text(
                        "SELECT operation_contract_version FROM a_class.target_breakdown WHERE id = :id"
                    ),
                    {"id": inherited_breakdown_id},
                ).scalar_one()
                == 1
            )
            connection.execute(
                text(
                    "UPDATE a_class.target_breakdown "
                    "SET target_amount = 1, operation_contract_version = NULL WHERE id = :id"
                ),
                {"id": inherited_breakdown_id},
            )
            assert (
                connection.execute(
                    text(
                        "SELECT operation_contract_version FROM a_class.target_breakdown WHERE id = :id"
                    ),
                    {"id": inherited_breakdown_id},
                ).scalar_one()
                == 1
            )
            wrong_version_savepoint = connection.begin_nested()
            with pytest.raises(Exception, match="contract version must match"):
                connection.execute(
                    text(
                        "INSERT INTO a_class.target_breakdown "
                        "(target_id, breakdown_type, platform_code, shop_id, period_start, period_end, "
                        "operation_contract_version) "
                        "VALUES (:target_id, 'shop', 'platform', 'shop', '2026-07-01', '2026-07-31', 2)"
                    ),
                    {"target_id": current_id},
                )
            wrong_version_savepoint.rollback()
            historical_target_insert_savepoint = connection.begin_nested()
            with pytest.raises(
                Exception, match="historical operation targets are read-only"
            ):
                connection.execute(
                    text(
                        "INSERT INTO a_class.sales_targets "
                        "(target_name, target_type, period_start, period_end) "
                        "VALUES ('New legacy target', 'operation', '2026-07-01', '2026-07-31')"
                    )
                )
            historical_target_insert_savepoint.rollback()
            for statement in (
                text(
                    "UPDATE a_class.sales_targets SET target_name = 'Changed' WHERE id = :id"
                ),
                text("DELETE FROM a_class.sales_targets WHERE id = :id"),
            ):
                savepoint = connection.begin_nested()
                with pytest.raises(
                    Exception, match="historical operation targets are read-only"
                ):
                    connection.execute(statement, {"id": historical_id})
                savepoint.rollback()
            for statement in (
                text(
                    "INSERT INTO a_class.target_breakdown "
                    "(target_id, breakdown_type, target_amount, target_quantity, achieved_amount, "
                    "achieved_quantity, achievement_rate) "
                    "VALUES (:target_id, 'time', 0, 0, 0, 0, 0)"
                ),
                text(
                    "UPDATE a_class.target_breakdown SET target_amount = 1 WHERE id = :id"
                ),
                text("DELETE FROM a_class.target_breakdown WHERE id = :id"),
            ):
                savepoint = connection.begin_nested()
                with pytest.raises(
                    Exception, match="historical operation breakdowns are read-only"
                ):
                    connection.execute(
                        statement,
                        {"id": historical_breakdown_id, "target_id": historical_id},
                    )
                savepoint.rollback()
            assert (
                connection.execute(
                    text(
                        "SELECT operation_contract_version FROM a_class.target_breakdown WHERE id = :id"
                    ),
                    {"id": historical_breakdown_id},
                ).scalar_one()
                is None
            )
            connection.execute(
                text(
                    "ALTER TABLE a_class.target_breakdown "
                    "DISABLE TRIGGER trg_enforce_operation_breakdown_contract"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO a_class.target_breakdown "
                    "(target_id, breakdown_type, target_amount, target_quantity, achieved_amount, "
                    "achieved_quantity, achievement_rate, operation_contract_version) "
                    "VALUES (:target_id, 'time', 0, 0, 0, 0, 0, NULL)"
                ),
                {"target_id": current_id},
            )
            connection.execute(
                text(
                    "ALTER TABLE a_class.target_breakdown "
                    "ENABLE TRIGGER trg_enforce_operation_breakdown_contract"
                )
            )

        with pytest.raises(
            migration_runner.MigrationSafetyError,
            match="invalid current operation contract data",
        ):
            migration_runner.assert_legacy_adoption_data_is_safe(database_url)
    finally:
        subprocess.run(["docker", "stop", "-t", "1", container_id], check=False)


def test_old_20260808_current_operation_overrides_are_backfilled_without_touching_history():
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
    database_url = (
        f"postgresql://current_test:current_test@127.0.0.1:{port}/current_test"
    )
    try:
        _wait_for_postgres(container_id)
        old_upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "alembic-current.ini",
                "upgrade",
                "current_schema_20260808_operation_performance_workbench",
            ],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": database_url},
            capture_output=True,
            text=True,
            check=False,
        )
        assert old_upgrade.returncode == 0, old_upgrade.stderr

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
                    "INSERT INTO core.dim_shops (platform_code, shop_id, shop_name) VALUES "
                    "('platform', 'current-shop', 'Current shop'), "
                    "('platform', 'legacy-shop', 'Legacy shop')"
                )
            )
            current_target_id = connection.execute(
                text(
                    "INSERT INTO a_class.sales_targets "
                    "(target_name, target_type, scope_type, period_start, period_end, metric_code, "
                    "metric_direction, metric_catalog_version) "
                    "VALUES ('Current target', 'operation', 'shop', '2026-08-01', '2026-08-31', "
                    "'reply', 'higher_better', 7) RETURNING id"
                )
            ).scalar_one()
            historical_target_id = connection.execute(
                text(
                    "INSERT INTO a_class.sales_targets "
                    "(target_name, target_type, period_start, period_end) "
                    "VALUES ('Historical target', 'operation', '2026-08-02', '2026-08-20') RETURNING id"
                )
            ).scalar_one()
            current_breakdown_id = connection.execute(
                text(
                    "INSERT INTO a_class.target_breakdown "
                    "(target_id, breakdown_type, platform_code, shop_id, period_start, period_end, "
                    "target_amount, target_quantity, achieved_amount, achieved_quantity, achievement_rate, "
                    "operation_contract_version) "
                    "VALUES (:target_id, 'shop', 'platform', 'current-shop', '2026-08-01', '2026-08-31', "
                    "123, 4, 45, 2, 36.5, 7) RETURNING id"
                ),
                {"target_id": current_target_id},
            ).scalar_one()
            historical_breakdown_id = connection.execute(
                text(
                    "INSERT INTO a_class.target_breakdown "
                    "(target_id, breakdown_type, platform_code, shop_id, period_start, period_end, "
                    "target_amount, target_quantity, achieved_amount, achieved_quantity, achievement_rate) "
                    "VALUES (:target_id, 'time', 'platform', 'legacy-shop', '2026-08-03', '2026-08-03', "
                    "99, 3, 11, 1, 11.1) RETURNING id"
                ),
                {"target_id": historical_target_id},
            ).scalar_one()
            history_before = connection.execute(
                text(
                    "SELECT target_id, breakdown_type, platform_code, shop_id, period_start, period_end, "
                    "target_amount, target_quantity, achieved_amount, achieved_quantity, achievement_rate "
                    "FROM a_class.target_breakdown WHERE id = :id"
                ),
                {"id": historical_breakdown_id},
            ).one()
            connection.execute(text("DROP INDEX a_class.uq_operation_shop_override"))
            connection.execute(
                text(
                    "ALTER TABLE a_class.target_breakdown "
                    "DROP COLUMN operation_contract_version"
                )
            )

        assert (
            migration_runner.run_current_schema_migrations(
                database_url,
                expected_source_revision=None,
                expected_source_fingerprint=None,
            )
            == "upgrade"
        )

        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT operation_contract_version FROM a_class.target_breakdown "
                        "WHERE id = :id"
                    ),
                    {"id": current_breakdown_id},
                ).scalar_one()
                == 7
            )
            history_after = connection.execute(
                text(
                    "SELECT target_id, breakdown_type, platform_code, shop_id, period_start, period_end, "
                    "target_amount, target_quantity, achieved_amount, achieved_quantity, achievement_rate "
                    "FROM a_class.target_breakdown WHERE id = :id"
                ),
                {"id": historical_breakdown_id},
            ).one()
            assert history_after == history_before
            assert (
                connection.execute(
                    text(
                        "SELECT operation_contract_version FROM a_class.target_breakdown "
                        "WHERE id = :id"
                    ),
                    {"id": historical_breakdown_id},
                ).scalar_one()
                is None
            )
    finally:
        subprocess.run(["docker", "stop", "-t", "1", container_id], check=False)


def test_20260808_preflight_rejects_invalid_current_override_when_contract_column_is_absent():
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
    database_url = (
        f"postgresql://current_test:current_test@127.0.0.1:{port}/current_test"
    )
    try:
        _wait_for_postgres(container_id)
        old_upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "alembic-current.ini",
                "upgrade",
                "current_schema_20260808_operation_performance_workbench",
            ],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": database_url},
            capture_output=True,
            text=True,
            check=False,
        )
        assert old_upgrade.returncode == 0, old_upgrade.stderr

        engine = create_engine(database_url)
        with engine.begin() as connection:
            current_target_id = connection.execute(
                text(
                    "INSERT INTO a_class.sales_targets "
                    "(target_name, target_type, scope_type, period_start, period_end, metric_code, "
                    "metric_direction, metric_catalog_version) "
                    "VALUES ('Current target', 'operation', 'shop', '2026-08-01', '2026-08-31', "
                    "'reply', 'higher_better', 7) RETURNING id"
                )
            ).scalar_one()
            # The old trigger only validates matching explicit versions, so a
            # versionless invalid time breakdown can exist in a 20260808 DB.
            connection.execute(
                text(
                    "INSERT INTO a_class.target_breakdown "
                    "(target_id, breakdown_type, period_start, period_end, target_amount, target_quantity, "
                    "achieved_amount, achieved_quantity, achievement_rate) "
                    "VALUES (:target_id, 'time', '2026-08-02', '2026-08-02', 0, 0, 0, 0, 0)"
                ),
                {"target_id": current_target_id},
            )
            connection.execute(text("DROP INDEX a_class.uq_operation_shop_override"))
            connection.execute(
                text(
                    "ALTER TABLE a_class.target_breakdown "
                    "DROP COLUMN operation_contract_version"
                )
            )

        preflight = subprocess.run(
            [
                sys.executable,
                "scripts/run_current_schema_migrations.py",
                "--database-url",
                database_url,
                "--preflight-only",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert preflight.returncode == 2
        assert "invalid current operation contract data" in preflight.stderr

        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT version_num FROM public.current_schema_alembic_version"
                    )
                ).scalar_one()
                == "current_schema_20260808_operation_performance_workbench"
            )
            assert "operation_contract_version" not in {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'a_class' AND table_name = 'target_breakdown'"
                    )
                )
            }
    finally:
        subprocess.run(["docker", "stop", "-t", "1", container_id], check=False)
