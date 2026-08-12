#!/usr/bin/env python3
"""Rebuild the approved local Docker database from an empty current-schema chain."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import psutil
from sqlalchemy.engine import make_url

try:
    from backend.utils.project_env import load_project_env
except ModuleNotFoundError:  # Direct `python scripts/...` execution on Windows.
    load_project_env = None  # type: ignore[assignment]

try:
    from scripts.local_migration_backup import (
        DEFAULT_BACKUP_DIRECTORY,
        DEFAULT_POSTGRES_CONTAINER,
        BackupValidationError,
        create_and_verify_backup,
        verify_backup_metadata,
    )
    from scripts.run_current_schema_migrations import (
        MigrationState,
        get_supported_current_revisions,
        probe_migration_state,
    )
except ModuleNotFoundError:  # Direct `python scripts/...` execution on Windows.
    from local_migration_backup import (  # type: ignore[no-redef]
        DEFAULT_BACKUP_DIRECTORY,
        DEFAULT_POSTGRES_CONTAINER,
        BackupValidationError,
        create_and_verify_backup,
        verify_backup_metadata,
    )
    from run_current_schema_migrations import (  # type: ignore[no-redef]
        MigrationState,
        get_supported_current_revisions,
        probe_migration_state,
    )


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_DATABASE = "xihong_erp"
EXPECTED_CONTAINER = DEFAULT_POSTGRES_CONTAINER
EXPECTED_PORT = 15432
CONFIRMATION_PHRASE = "REBUILD_LOCAL_XIHONG_ERP"
DEFAULT_RECEIPT_DIRECTORY = DEFAULT_BACKUP_DIRECTORY / "rebuild-receipts"


class RebuildSafetyError(RuntimeError):
    """Raised before an unsafe local database rebuild can begin."""


def _safe_identifier(value: str | None, field: str) -> str:
    if not value or not value.replace("_", "").isalnum():
        raise RebuildSafetyError(f"local rebuild {field} is invalid")
    return value


def _validate_local_target(database_url: str) -> tuple[str, str]:
    url = make_url(database_url)
    if url.drivername.split("+", 1)[0] != "postgresql":
        raise RebuildSafetyError("local rebuild requires a PostgreSQL URL")
    if url.host not in {"127.0.0.1", "localhost"} or url.port != EXPECTED_PORT:
        raise RebuildSafetyError("local rebuild requires the loopback PostgreSQL port")
    if url.query:
        raise RebuildSafetyError("local rebuild URL must not contain query overrides")
    database = _safe_identifier(url.database, "database")
    username = _safe_identifier(url.username, "username")
    if database != EXPECTED_DATABASE:
        raise RebuildSafetyError("local rebuild only permits xihong_erp")
    return database, username


def _normalized_local_database_url(database_url: str) -> str:
    """Use a sync SQLAlchemy PostgreSQL URL after target validation."""
    url = make_url(database_url)
    _validate_local_target(database_url)
    return str(url.set(drivername="postgresql"))


def _docker_context_endpoint() -> str:
    result = subprocess.run(
        ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _assert_local_docker_daemon() -> None:
    endpoint = os.getenv("DOCKER_HOST", "").strip() or _docker_context_endpoint()
    if not endpoint.casefold().startswith("npipe:////./pipe/"):
        raise RebuildSafetyError("local rebuild requires the local Docker daemon")


def _local_collection_backend_running(process_iterator: Callable[[], Iterable[Any]]) -> bool:
    for process in process_iterator():
        try:
            command = " ".join(str(part) for part in process.cmdline()).lower()
        except Exception:
            continue
        if "start_collection_formal.ps1" in command or "run.py --local" in command:
            return True
    return False


def _docker_result(
    command: list[str], docker_runner: Callable[..., Any], *, message: str
) -> Any:
    result = docker_runner(command, capture_output=True, text=True, check=False)
    if getattr(result, "returncode", 1) != 0:
        raise RebuildSafetyError(message)
    return result


def _assert_no_active_connections(
    database: str,
    username: str,
    docker_runner: Callable[..., Any],
) -> None:
    result = _docker_result(
        [
            "docker",
            "exec",
            EXPECTED_CONTAINER,
            "psql",
            "-U",
            username,
            "-d",
            "postgres",
            "-At",
            "-c",
            (
                "SELECT count(*) FROM pg_stat_activity "
                f"WHERE datname = '{database}' AND pid <> pg_backend_pid()"
            ),
        ],
        docker_runner,
        message="local rebuild could not inspect active connections",
    )
    try:
        active_connections = int(str(result.stdout).strip() or "0")
    except ValueError as exc:
        raise RebuildSafetyError("local rebuild connection inspection returned invalid data") from exc
    if active_connections:
        raise RebuildSafetyError("local rebuild refused because the database has active connections")


def _assert_target_container_port_mapping(docker_runner: Callable[..., Any]) -> None:
    result = _docker_result(
        [
            "docker",
            "inspect",
            "--format",
            "{{json .NetworkSettings.Ports}}",
            EXPECTED_CONTAINER,
        ],
        docker_runner,
        message="local rebuild could not inspect the target container",
    )
    try:
        mappings = json.loads(result.stdout)
        postgres_mappings = mappings["5432/tcp"]
    except (TypeError, ValueError, KeyError) as exc:
        raise RebuildSafetyError("local rebuild target container port mapping is invalid") from exc
    if not isinstance(postgres_mappings, list) or not any(
        isinstance(mapping, dict)
        and mapping.get("HostPort") == str(EXPECTED_PORT)
        for mapping in postgres_mappings
    ):
        raise RebuildSafetyError(
            "local rebuild target container port mapping does not match the database URL"
        )


def _set_database_connection_policy(
    database: str,
    username: str,
    allow_connections: bool,
    docker_runner: Callable[..., Any],
) -> None:
    policy = "true" if allow_connections else "false"
    _docker_result(
        [
            "docker",
            "exec",
            EXPECTED_CONTAINER,
            "psql",
            "-U",
            username,
            "-d",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            f'ALTER DATABASE "{database}" WITH ALLOW_CONNECTIONS {policy}',
        ],
        docker_runner,
        message="local rebuild could not update the database connection policy",
    )


def _run_checked_command(
    command: list[str],
    command_runner: Callable[..., Any],
    *,
    environment: dict[str, str],
    message: str,
) -> Any:
    result = command_runner(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if getattr(result, "returncode", 1) != 0:
        raise RebuildSafetyError(message)
    return result


def _write_receipt(
    receipt_directory: Path,
    *,
    database: str,
    backup_metadata: dict[str, Any],
    current_revision: str,
    dashboard_check: dict[str, Any],
) -> Path:
    receipt_directory.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    receipt_path = receipt_directory / f"{database}-{created_at}.json"
    receipt_path.write_text(
        json.dumps(
            {
                "created_at": created_at,
                "database": database,
                "backup_sha256": backup_metadata["backup_sha256"],
                "current_revision": current_revision,
                "dashboard_ready": bool(dashboard_check.get("ready")),
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )
    return receipt_path


def rebuild_local_current_schema(
    database_url: str,
    *,
    confirmation: str,
    docker_runner: Callable[..., Any] = subprocess.run,
    command_runner: Callable[..., Any] = subprocess.run,
    process_iterator: Callable[[], Iterable[Any]] = psutil.process_iter,
    migration_state_probe: Callable[[str], MigrationState] = probe_migration_state,
    backup_creator: Callable[..., dict[str, Any]] = create_and_verify_backup,
    backup_verifier: Callable[..., dict[str, Any]] = verify_backup_metadata,
    receipt_directory: Path = DEFAULT_RECEIPT_DIRECTORY,
) -> dict[str, str]:
    """Back up, rebuild, migrate, bootstrap, and receipt the fixed local target."""
    if confirmation != CONFIRMATION_PHRASE:
        raise RebuildSafetyError("local rebuild requires the exact confirmation phrase")
    database, username = _validate_local_target(database_url)
    database_url = _normalized_local_database_url(database_url)
    _assert_local_docker_daemon()
    if _local_collection_backend_running(process_iterator):
        raise RebuildSafetyError("local rebuild refused while the collection backend is running")
    _assert_target_container_port_mapping(docker_runner)
    _assert_no_active_connections(database, username, docker_runner)

    state = migration_state_probe(database_url)
    try:
        backup_metadata = backup_creator(
            database_url,
            state,
            docker_container=EXPECTED_CONTAINER,
            docker_runner=docker_runner,
        )
        backup_verifier(Path(backup_metadata["metadata_path"]), state)
        if backup_metadata.get("source_database") != database:
            raise RebuildSafetyError(
                "local rebuild backup source database does not match target database"
            )
    except BackupValidationError as exc:
        raise RebuildSafetyError("local rebuild backup validation failed") from exc
    connections_disabled = False
    try:
        _set_database_connection_policy(database, username, False, docker_runner)
        connections_disabled = True
        _assert_no_active_connections(database, username, docker_runner)
        _docker_result(
            [
                "docker",
                "exec",
                EXPECTED_CONTAINER,
                "dropdb",
                "-U",
                username,
                "--maintenance-db=postgres",
                database,
            ],
            docker_runner,
            message="local rebuild could not drop xihong_erp",
        )
        connections_disabled = False
    except Exception:
        if connections_disabled:
            try:
                _set_database_connection_policy(database, username, True, docker_runner)
            except RebuildSafetyError:
                pass
        raise
    _docker_result(
        [
            "docker",
            "exec",
            EXPECTED_CONTAINER,
            "createdb",
            "-U",
            username,
            database,
        ],
        docker_runner,
        message="local rebuild could not create xihong_erp",
    )

    environment = {**os.environ, "DATABASE_URL": database_url}
    _run_checked_command(
        [sys.executable, "scripts/run_current_schema_migrations.py"],
        command_runner,
        environment=environment,
        message="local rebuild current-schema migration failed",
    )
    _run_checked_command(
        [sys.executable, "scripts/bootstrap_postgresql_dashboard.py", "--module", "business_overview"],
        command_runner,
        environment=environment,
        message="local rebuild dashboard bootstrap failed",
    )
    dashboard_result = _run_checked_command(
        [
            sys.executable,
            "scripts/bootstrap_postgresql_dashboard.py",
            "--module",
            "business_overview",
            "--check",
            "--json",
        ],
        command_runner,
        environment=environment,
        message="local rebuild dashboard check failed",
    )
    try:
        dashboard_check = json.loads(dashboard_result.stdout)
    except (TypeError, ValueError) as exc:
        raise RebuildSafetyError("local rebuild dashboard check returned invalid data") from exc
    if not dashboard_check.get("ready"):
        raise RebuildSafetyError("local rebuild dashboard assets are not ready")

    rebuilt_state = migration_state_probe(database_url)
    if (
        not rebuilt_state.current_revision
        or rebuilt_state.current_revision not in get_supported_current_revisions()
    ):
        raise RebuildSafetyError("local rebuild did not produce a current-schema revision")
    receipt_path = _write_receipt(
        receipt_directory,
        database=database,
        backup_metadata=backup_metadata,
        current_revision=rebuilt_state.current_revision,
        dashboard_check=dashboard_check,
    )
    return {
        "database": database,
        "backup_sha256": str(backup_metadata["backup_sha256"]),
        "receipt_path": str(receipt_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)
    if load_project_env is not None:
        load_project_env(ROOT, profile="collection", override=True)
    database_url = args.database_url or os.getenv("DATABASE_URL")
    try:
        result = rebuild_local_current_schema(
            (database_url or "").strip(), confirmation=args.confirm
        )
    except (RebuildSafetyError, BackupValidationError) as exc:
        print(f"[FAIL] local rebuild refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
