"""Create and validate local PostgreSQL migration backups through Docker."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.engine import make_url


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKUP_DIRECTORY = ROOT / "backups" / "local-migration"
DEFAULT_POSTGRES_CONTAINER = "xihong_erp_postgres"


class BackupValidationError(RuntimeError):
    """Raised when a local migration backup cannot be proven restorable."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run_docker(
    command: list[str], docker_runner: Callable[..., Any]
) -> Any:
    result = docker_runner(command, capture_output=True, text=True, check=False)
    if getattr(result, "returncode", 1) != 0:
        raise BackupValidationError("migration backup command failed")
    return result


def _safe_timestamp(now: Callable[[], str] | None) -> str:
    return now() if now is not None else datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def create_and_verify_backup(
    database_url: str,
    state: Any,
    *,
    backup_directory: Path = DEFAULT_BACKUP_DIRECTORY,
    docker_container: str | None = None,
    docker_runner: Callable[..., Any] = subprocess.run,
    now: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Create a custom-format dump and prove it is readable with `pg_restore --list`."""
    url = make_url(database_url)
    database_name = url.database
    username = url.username
    if not database_name or not username:
        raise BackupValidationError("migration backup requires a database name and username")
    if any(not value.replace("_", "").replace("-", "").isalnum() for value in (database_name, username)):
        raise BackupValidationError("migration backup database identifier is invalid")

    container = docker_container or os.getenv(
        "LOCAL_POSTGRES_CONTAINER", DEFAULT_POSTGRES_CONTAINER
    )
    timestamp = _safe_timestamp(now)
    filename = f"{database_name}-{timestamp}.dump"
    container_path = f"/tmp/{filename}"
    backup_directory.mkdir(parents=True, exist_ok=True)
    backup_path = backup_directory / filename
    metadata_path = backup_path.with_suffix(".json")

    try:
        _run_docker(
            [
                "docker",
                "exec",
                container,
                "pg_dump",
                "-U",
                username,
                "-Fc",
                "-f",
                container_path,
                database_name,
            ],
            docker_runner,
        )
        _run_docker(
            ["docker", "cp", f"{container}:{container_path}", str(backup_path)],
            docker_runner,
        )
        if not backup_path.exists() or backup_path.stat().st_size == 0:
            raise BackupValidationError("migration backup archive was not created")
        restore = docker_runner(
            ["docker", "exec", container, "pg_restore", "--list", container_path],
            capture_output=True,
            text=True,
            check=False,
        )
        if getattr(restore, "returncode", 1) != 0:
            raise BackupValidationError("migration backup pg_restore --list failed")
    finally:
        docker_runner(
            ["docker", "exec", container, "rm", "-f", container_path],
            capture_output=True,
            text=True,
            check=False,
        )

    metadata = {
        "backup_path": str(backup_path),
        "metadata_path": str(metadata_path),
        "backup_sha256": _sha256(backup_path),
        "created_at": timestamp,
        "source_database": database_name,
        "legacy_revision": state.legacy_revision,
        "current_revision": state.current_revision,
        "schema_fingerprint": state.schema_fingerprint,
        "verification": "pg_restore_list_passed",
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    verify_backup_metadata(metadata_path, state)
    return metadata


def verify_backup_metadata(metadata_path: Path, state: Any) -> dict[str, Any]:
    """Check the recorded archive and schema evidence before allowing a write."""
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        backup_path = Path(metadata["backup_path"])
    except (OSError, TypeError, ValueError, KeyError) as exc:
        raise BackupValidationError("migration backup metadata is unreadable") from exc
    if metadata.get("verification") != "pg_restore_list_passed":
        raise BackupValidationError("migration backup readability verification is missing")
    if not backup_path.exists() or _sha256(backup_path) != metadata.get("backup_sha256"):
        raise BackupValidationError("migration backup archive hash does not match metadata")
    for field in ("legacy_revision", "current_revision", "schema_fingerprint"):
        if metadata.get(field) != getattr(state, field):
            raise BackupValidationError(
                f"migration backup {field.replace('_', ' ')} does not match current database"
            )
    return metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--verify-metadata", type=Path)
    args = parser.parse_args(argv)
    if args.verify_metadata is None:
        parser.error("--verify-metadata is required for standalone verification")
    try:
        metadata = json.loads(args.verify_metadata.read_text(encoding="utf-8"))
        archive = Path(metadata["backup_path"])
        if metadata.get("verification") != "pg_restore_list_passed":
            raise BackupValidationError("migration backup readability verification is missing")
        if not archive.exists() or _sha256(archive) != metadata.get("backup_sha256"):
            raise BackupValidationError("migration backup archive hash does not match metadata")
    except (OSError, KeyError, TypeError, ValueError, BackupValidationError) as exc:
        print(f"[FAIL] migration backup verification failed: {exc}")
        return 2
    print("[OK] migration backup metadata verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
