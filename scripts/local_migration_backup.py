"""Create and validate PostgreSQL migration backups.

Two dump transports are supported, because the same backup has to work in two
different places:

- ``docker`` (default): the dump runs **inside the PostgreSQL container**
  (``docker exec ... pg_dump``) and is copied back with ``docker cp``. This is
  the production path: the production database does not expose 5432 to the
  host, so the dump can only be produced from within the server/container.
- ``direct``: ``pg_dump`` / ``pg_restore`` client binaries talk to the given
  URL directly. This is the local-database path (e.g. a local PostgreSQL
  instance reachable over TCP) and the in-container path (a release container
  that already has ``postgresql-client`` installed and can reach the database
  over the compose network).

Both transports end with the same restore check: ``pg_restore --list`` must
exit 0, otherwise the archive is rejected as unrestorable.

Every run writes into its own timestamped directory
(``<backup_directory>/backup_<timestamp>/``) so a new backup never overwrites
an older one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse


try:  # SQLAlchemy is optional: the CLI must also run on a bare server python.
    from sqlalchemy.engine import make_url
except ModuleNotFoundError:  # pragma: no cover - exercised on minimal hosts
    make_url = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKUP_DIRECTORY = ROOT / "backups" / "local-migration"
DEFAULT_POSTGRES_CONTAINER = "xihong_erp_postgres"

# 被别的会话长事务锁住时，pg_dump 会无限等锁 ⇒ 备份看起来"失败"，实际是被拖死。
# 给它一个服务端锁等待上限：拿不到锁就明确报错退出，而不是无限期挂住。
LOCK_TIMEOUT_ENV = "PGOPTIONS=-c lock_timeout=60s"
DOCKER_COMMAND_TIMEOUT_SECONDS = 300
# direct 传输同样必须有上限，否则本地/容器内直连备份也可能被拖死。
CLIENT_COMMAND_TIMEOUT_SECONDS = 300

DUMP_MODE_DOCKER = "docker"
DUMP_MODE_DIRECT = "direct"
DUMP_MODES = (DUMP_MODE_DOCKER, DUMP_MODE_DIRECT)

_SECRET_PATTERN = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key)\s*[=:]\s*([^\s'\"]+)"
)
_ADDRESS_PATTERN = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b")
_URL_PATTERN = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://\S+")


class BackupValidationError(RuntimeError):
    """Raised when a local migration backup cannot be proven restorable."""


@dataclass(frozen=True)
class BackupState:
    """The migration state evidence recorded next to a backup."""

    database_empty: bool = False
    current_revision: str | None = None
    legacy_revision: str | None = None
    schema_fingerprint: str | None = None


def _parse_database_target(database_url: str) -> tuple[str, str]:
    """Return ``(username, database)`` without requiring SQLAlchemy."""
    if make_url is not None:
        url = make_url(database_url)
        return url.username or "", url.database or ""
    parsed = urlparse(database_url)
    database = (parsed.path or "").lstrip("/")
    username = unquote(parsed.username) if parsed.username else ""
    return username, database


def _parse_connection_parts(
    database_url: str,
) -> tuple[str, int, str, str, str]:
    """Return ``(host, port, username, password, database)`` for the direct transport."""
    if make_url is not None:
        url = make_url(database_url)
        return (
            url.host or "localhost",
            int(url.port or 5432),
            url.username or "",
            url.password or "",
            url.database or "",
        )
    parsed = urlparse(database_url)
    database = (parsed.path or "").lstrip("/")
    username = unquote(parsed.username) if parsed.username else ""
    password = unquote(parsed.password) if parsed.password else ""
    return (
        parsed.hostname or "localhost",
        int(parsed.port or 5432),
        username,
        password,
        database,
    )


def _safe_failure_reason(stderr: str | None) -> str:
    """把 docker/pg_dump 的报错压成一行**不含连接细节**的摘要。

    运维要看到"到底为什么失败"（例如 lock timeout），
    但不能把主机地址、库名、凭据泄露到控制台或日志里。
    """
    if not stderr:
        return "no diagnostic output"
    text = stderr.strip()
    if not text:
        return "no diagnostic output"
    first_line = text.splitlines()[0].strip()
    first_line = _URL_PATTERN.sub("<connection>", first_line)
    first_line = _SECRET_PATTERN.sub(r"\1=***", first_line)
    first_line = _ADDRESS_PATTERN.sub("<addr>", first_line)
    return first_line[:200] or "no diagnostic output"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_docker(command: list[str], docker_runner: Callable[..., Any]) -> Any:
    try:
        result = docker_runner(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=DOCKER_COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise BackupValidationError(
            "migration backup command timed out after "
            f"{DOCKER_COMMAND_TIMEOUT_SECONDS}s"
        ) from exc
    except OSError as exc:
        raise BackupValidationError(
            f"migration backup command could not be started: {exc.__class__.__name__}"
        ) from exc
    if getattr(result, "returncode", 1) != 0:
        raise BackupValidationError(
            "migration backup command failed: "
            f"{_safe_failure_reason(getattr(result, 'stderr', None))}"
        )
    return result


def _safe_timestamp(now: Callable[[], str] | None) -> str:
    return (
        now()
        if now is not None
        else datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )


def _create_run_directory(base_directory: Path, timestamp: str) -> Path:
    """Create a fresh, timestamped directory so history is never overwritten."""
    base_directory.mkdir(parents=True, exist_ok=True)
    run_directory = base_directory / f"backup_{timestamp}"
    suffix = 1
    while run_directory.exists():
        run_directory = base_directory / f"backup_{timestamp}_{suffix}"
        suffix += 1
    run_directory.mkdir(parents=True)
    return run_directory


def _client_environment(database_url: str) -> dict[str, str]:
    """Build the libpq environment for the direct transport.

    The password goes through ``PGPASSWORD`` (environment) instead of the
    command line, so it never shows up in the process list.
    """
    host, port, username, password, database = _parse_connection_parts(database_url)
    env = dict(os.environ)
    env["PGHOST"] = host
    env["PGPORT"] = str(port)
    env["PGUSER"] = username
    env["PGDATABASE"] = database
    env["PGOPTIONS"] = LOCK_TIMEOUT_ENV.split("=", 1)[1]
    if password:
        env["PGPASSWORD"] = password
    else:
        env.pop("PGPASSWORD", None)
    return env


def _run_client(
    command: list[str],
    *,
    env: dict[str, str],
    runner: Callable[..., Any],
    failure_message: str = "migration backup command failed",
) -> Any:
    try:
        result = runner(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=CLIENT_COMMAND_TIMEOUT_SECONDS,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise BackupValidationError(
            "migration backup command timed out after "
            f"{CLIENT_COMMAND_TIMEOUT_SECONDS}s"
        ) from exc
    except OSError as exc:
        raise BackupValidationError(
            f"migration backup command could not be started: {exc.__class__.__name__}"
        ) from exc
    if getattr(result, "returncode", 1) != 0:
        raise BackupValidationError(
            f"{failure_message}: {_safe_failure_reason(getattr(result, 'stderr', None))}"
        )
    return result


def _dump_with_docker(
    database_url: str,
    *,
    username: str,
    database_name: str,
    backup_path: Path,
    container: str,
    docker_runner: Callable[..., Any],
) -> None:
    container_path = f"/tmp/{backup_path.name}"
    try:
        _run_docker(
            [
                "docker",
                "exec",
                "-e",
                LOCK_TIMEOUT_ENV,
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
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=DOCKER_COMMAND_TIMEOUT_SECONDS,
        )
        if getattr(restore, "returncode", 1) != 0:
            raise BackupValidationError("migration backup pg_restore --list failed")
    finally:
        docker_runner(
            ["docker", "exec", container, "rm", "-f", container_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=DOCKER_COMMAND_TIMEOUT_SECONDS,
        )


def _dump_with_client(
    database_url: str,
    *,
    database_name: str,
    backup_path: Path,
    runner: Callable[..., Any],
) -> None:
    env = _client_environment(database_url)
    _run_client(
        ["pg_dump", "-Fc", "-f", str(backup_path), database_name],
        env=env,
        runner=runner,
    )
    if not backup_path.exists() or backup_path.stat().st_size == 0:
        raise BackupValidationError("migration backup archive was not created")
    _run_client(
        ["pg_restore", "--list", str(backup_path)],
        env=env,
        runner=runner,
        failure_message="migration backup pg_restore --list failed",
    )


def create_and_verify_backup(
    database_url: str,
    state: Any,
    *,
    backup_directory: Path = DEFAULT_BACKUP_DIRECTORY,
    docker_container: str | None = None,
    docker_runner: Callable[..., Any] = subprocess.run,
    now: Callable[[], str] | None = None,
    dump_mode: str = DUMP_MODE_DOCKER,
    client_runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    """Create a custom-format dump and prove it is readable with `pg_restore --list`."""
    if dump_mode not in DUMP_MODES:
        raise BackupValidationError(
            f"migration backup dump mode is invalid: {dump_mode}"
        )
    username, database_name = _parse_database_target(database_url)
    if not database_name or not username:
        raise BackupValidationError(
            "migration backup requires a database name and username"
        )
    if any(
        not value.replace("_", "").replace("-", "").isalnum()
        for value in (database_name, username)
    ):
        raise BackupValidationError("migration backup database identifier is invalid")

    container = docker_container or os.getenv(
        "LOCAL_POSTGRES_CONTAINER", DEFAULT_POSTGRES_CONTAINER
    )
    timestamp = _safe_timestamp(now)
    run_directory = _create_run_directory(Path(backup_directory), timestamp)
    filename = f"{database_name}-{timestamp}.dump"
    backup_path = run_directory / filename
    metadata_path = backup_path.with_suffix(".json")

    if dump_mode == DUMP_MODE_DOCKER:
        _dump_with_docker(
            database_url,
            username=username,
            database_name=database_name,
            backup_path=backup_path,
            container=container,
            docker_runner=docker_runner,
        )
    else:
        _dump_with_client(
            database_url,
            database_name=database_name,
            backup_path=backup_path,
            runner=client_runner,
        )

    metadata = {
        "backup_path": str(backup_path),
        "metadata_path": str(metadata_path),
        "backup_sha256": _sha256(backup_path),
        "created_at": timestamp,
        "dump_mode": dump_mode,
        "source_database": database_name,
        "legacy_revision": getattr(state, "legacy_revision", None),
        "current_revision": getattr(state, "current_revision", None),
        "schema_fingerprint": getattr(state, "schema_fingerprint", None),
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
        raise BackupValidationError(
            "migration backup readability verification is missing"
        )
    if not backup_path.exists() or _sha256(backup_path) != metadata.get(
        "backup_sha256"
    ):
        raise BackupValidationError(
            "migration backup archive hash does not match metadata"
        )
    if state is None:
        # 没有可比的迁移状态（服务器上没有数据库连通性时）时，
        # 只能校验归档本身；可恢复性判据仍然是 pg_restore --list 退出码 0。
        return metadata
    for field in ("legacy_revision", "current_revision", "schema_fingerprint"):
        if metadata.get(field) != getattr(state, field, None):
            raise BackupValidationError(
                f"migration backup {field.replace('_', ' ')} does not match current database"
            )
    return metadata


def _load_state_file(path: Path) -> BackupState:
    try:
        # utf-8-sig：带 BOM 的状态文件也能读（Windows 上重定向写出的文件常常带 BOM）。
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, TypeError, ValueError) as exc:
        raise BackupValidationError("migration backup state file is unreadable") from exc
    if not isinstance(data, dict):
        raise BackupValidationError("migration backup state file is invalid")
    return BackupState(
        database_empty=bool(data.get("database_empty", False)),
        current_revision=data.get("current_revision"),
        legacy_revision=data.get("legacy_revision"),
        schema_fingerprint=data.get("schema_fingerprint"),
    )


def _probe_state(database_url: str) -> BackupState | None:
    """Read the current migration state (best effort, read-only)."""
    probe: Callable[[str], Any] | None = None
    for module_name in (
        "scripts.run_current_schema_migrations",
        "run_current_schema_migrations",
    ):
        try:
            module = __import__(module_name, fromlist=["probe_migration_state"])
        except ImportError:
            continue
        probe = getattr(module, "probe_migration_state", None)
        if probe is not None:
            break
    if probe is None:
        return None
    try:
        state = probe(database_url)
    except Exception:  # noqa: BLE001 - the probe is best effort by design
        return None
    return BackupState(
        database_empty=bool(getattr(state, "database_empty", False)),
        current_revision=getattr(state, "current_revision", None),
        legacy_revision=getattr(state, "legacy_revision", None),
        schema_fingerprint=getattr(state, "schema_fingerprint", None),
    )


def _print_state(database_url: str) -> int:
    state = _probe_state(database_url)
    if state is None:
        print("[FAIL] Could not read the current migration state")
        return 2
    print(
        json.dumps(
            {
                "database_empty": state.database_empty,
                "current_revision": state.current_revision,
                "legacy_revision": state.legacy_revision,
                "schema_fingerprint": state.schema_fingerprint,
            },
            ensure_ascii=True,
        )
    )
    return 0


def _create_backup(args: argparse.Namespace) -> int:
    database_url = (args.database_url or "").strip()
    if not database_url:
        print("[FAIL] --database-url (or DATABASE_URL) is required to create a backup")
        return 2

    state: BackupState | None = None
    if args.state_file is not None:
        try:
            state = _load_state_file(args.state_file)
        except BackupValidationError as exc:
            print(f"[FAIL] {exc}")
            return 2
    else:
        state = _probe_state(database_url)

    if state is None and args.require_state:
        print(
            "[FAIL] Could not determine the current migration state "
            "(pass --state-file or drop --require-state)"
        )
        return 2

    try:
        metadata = create_and_verify_backup(
            database_url,
            state,
            backup_directory=args.backup_directory,
            docker_container=args.docker_container,
            dump_mode=args.dump_mode,
        )
    except BackupValidationError as exc:
        print(f"[FAIL] migration backup failed: {exc}")
        return 2

    print(f"[OK] migration backup created: {metadata['backup_path']}")
    print(f"[OK] migration backup metadata: {metadata['metadata_path']}")
    print("[OK] migration backup readability verification passed (pg_restore --list)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--verify-metadata", type=Path)
    parser.add_argument(
        "--create",
        action="store_true",
        help="Create a new backup and verify that it can be restored",
    )
    parser.add_argument(
        "--print-state",
        action="store_true",
        help="Print the current migration state as JSON (read-only)",
    )
    parser.add_argument(
        "--backup-directory",
        type=Path,
        default=DEFAULT_BACKUP_DIRECTORY,
        help="Directory that receives the timestamped backup run directory",
    )
    parser.add_argument(
        "--dump-mode",
        choices=DUMP_MODES,
        default=os.getenv("MIGRATION_BACKUP_DUMP_MODE", DUMP_MODE_DOCKER),
        help="docker: pg_dump inside the postgres container; direct: pg_dump client",
    )
    parser.add_argument(
        "--docker-container",
        default=os.getenv("LOCAL_POSTGRES_CONTAINER", DEFAULT_POSTGRES_CONTAINER),
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        help="JSON file with the migration state to record next to the backup",
    )
    parser.add_argument(
        "--require-state",
        action="store_true",
        help="Fail when the current migration state cannot be determined",
    )
    args = parser.parse_args(argv)

    if args.print_state:
        database_url = (args.database_url or "").strip()
        if not database_url:
            print("[FAIL] --database-url (or DATABASE_URL) is required")
            return 2
        return _print_state(database_url)

    if args.create:
        return _create_backup(args)

    if args.verify_metadata is None:
        parser.error(
            "one of --create, --print-state or --verify-metadata is required"
        )
    try:
        metadata = json.loads(args.verify_metadata.read_text(encoding="utf-8"))
        archive = Path(metadata["backup_path"])
        if metadata.get("verification") != "pg_restore_list_passed":
            raise BackupValidationError(
                "migration backup readability verification is missing"
            )
        if not archive.exists() or _sha256(archive) != metadata.get("backup_sha256"):
            raise BackupValidationError(
                "migration backup archive hash does not match metadata"
            )
    except (OSError, KeyError, TypeError, ValueError, BackupValidationError) as exc:
        print(f"[FAIL] migration backup verification failed: {exc}")
        return 2
    print("[OK] migration backup metadata verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
