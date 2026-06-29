from __future__ import annotations

import hashlib
import logging
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect as sa_inspect, or_, select
from sqlalchemy.engine import make_url

from backend.models.database import DATABASE_URL, SessionLocal
from backend.services.cloud_b_class_auto_sync_runtime import (
    CloudBClassAutoSyncRuntime,
    should_enable_cloud_sync_worker,
)
from backend.services.cloud_b_class_auto_sync_worker import CloudBClassAutoSyncWorker
from backend.services.cloud_b_class_mirror_manager import CloudBClassMirrorManager
from backend.services.cloud_b_class_sync_checkpoint_service import (
    CloudBClassSyncCheckpointService,
)
from backend.services.cloud_b_class_sync_service import (
    CloudBClassSyncService,
    SQLAlchemyBClassSourceReader,
    SQLAlchemyCloudWriter,
)
from modules.core.db import CloudBClassSyncTask


logger = logging.getLogger(__name__)


class NoOpCloudBClassMirrorManager:
    """Dry-run mirror manager that never touches the cloud database."""

    def ensure_cloud_schema_exists(self) -> None:
        return None

    def ensure_cloud_mirror_table(self, table_name: str, data_domain: str) -> None:
        return None


def _build_checkpoint_scope_key(cloud_database_url: str | None, dry_run: bool) -> str:
    if dry_run:
        return "cloud_sync:dry_run"

    if not cloud_database_url:
        return "cloud_sync:local"

    parsed = make_url(cloud_database_url)
    identity = (
        f"{parsed.drivername.split('+', 1)[0]}://"
        f"{parsed.host or ''}:{parsed.port or ''}/"
        f"{parsed.database or ''}"
    )
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]
    return f"cloud_sync:{digest}"


def get_current_checkpoint_scope_from_env(*, dry_run: bool = False) -> str:
    return _build_checkpoint_scope_key(os.getenv("CLOUD_DATABASE_URL"), dry_run=dry_run)


def _tcp_probe(host: str, port: int, timeout_seconds: float = 1.0) -> tuple[bool, str | None]:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True, None
    except Exception as exc:
        return False, str(exc)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _get_code_alembic_heads() -> set[str]:
    cfg = Config(str(_project_root() / "alembic.ini"))
    cfg.set_main_option("script_location", str(_project_root() / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    return set(script.get_heads())


def _get_database_alembic_revisions(engine) -> set[str]:
    revisions: set[str] = set()
    with engine.begin() as conn:
        rows = conn.exec_driver_sql(
            """
            SELECT table_schema
            FROM information_schema.tables
            WHERE table_name = 'alembic_version'
            ORDER BY table_schema
            """
        ).fetchall()
        for row in rows:
            schema = row[0]
            result = conn.exec_driver_sql(
                f'SELECT version_num FROM "{schema}".alembic_version'
            )
            revisions.update(str(item[0]) for item in result.fetchall())
    return revisions


def _run_alembic_upgrade(database_url: str, target: str = "heads") -> None:
    env = dict(os.environ)
    env["DATABASE_URL"] = database_url
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", target],
        cwd=_project_root(),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(detail or f"alembic upgrade {target} failed")


def _check_alembic_revision(
    engine,
    *,
    label: str,
    database_url: str | None = None,
    allow_auto_migration: bool = False,
) -> dict[str, str | bool | None]:
    expected_heads = _get_code_alembic_heads()
    current_revisions = _get_database_alembic_revisions(engine)
    if current_revisions == expected_heads:
        return {
            "ok": True,
            "detail": ",".join(sorted(current_revisions)) if current_revisions else "no revisions",
        }

    detail = (
        f"{label} revision mismatch: current={','.join(sorted(current_revisions)) or 'missing'} "
        f"expected={','.join(sorted(expected_heads)) or 'missing'}"
    )
    if allow_auto_migration and database_url:
        _run_alembic_upgrade(database_url, "heads")
        return {
            "ok": True,
            "detail": "auto-migrated to heads",
        }
    return {
        "ok": False,
        "detail": detail,
    }


def run_cloud_sync_startup_checks_from_env() -> dict:
    checks: dict[str, dict[str, str | bool | None]] = {}
    status = "ok"

    local_engine = None
    try:
        local_engine = create_engine(DATABASE_URL)
        with local_engine.begin() as conn:
            conn.exec_driver_sql("SELECT 1")
        inspector = sa_inspect(local_engine)
        table_names = set(inspector.get_table_names())
        required_tables = {
            "cloud_b_class_sync_checkpoints",
            "cloud_b_class_sync_runs",
            "cloud_b_class_sync_tasks",
        }
        missing_tables = sorted(required_tables - table_names)
        checks["local_database"] = {
            "ok": True,
            "detail": "connected",
        }
        checks["cloud_sync_state_tables"] = {
            "ok": not missing_tables,
            "detail": None if not missing_tables else f"missing: {', '.join(missing_tables)}",
        }
        if missing_tables:
            status = "degraded"
        revision_check = _check_alembic_revision(
            local_engine,
            label="local",
            database_url=DATABASE_URL,
            allow_auto_migration=False,
        )
        checks["local_alembic_revision"] = revision_check
        if not revision_check["ok"]:
            status = "error"
    except Exception as exc:
        checks["local_database"] = {
            "ok": False,
            "detail": str(exc),
        }
        checks["cloud_sync_state_tables"] = {
            "ok": False,
            "detail": "local database unavailable",
        }
        checks["local_alembic_revision"] = {
            "ok": False,
            "detail": "local database unavailable",
        }
        status = "error"
    finally:
        if local_engine is not None:
            local_engine.dispose()

    cloud_database_url = os.getenv("CLOUD_DATABASE_URL")
    if cloud_database_url:
        try:
            parsed = make_url(cloud_database_url)
            checks["cloud_database_url"] = {
                "ok": True,
                "detail": f"{parsed.drivername.split('+', 1)[0]}://{parsed.host or ''}:{parsed.port or 5432}/{parsed.database or ''}",
            }
            host = parsed.host or "127.0.0.1"
            port = int(parsed.port or 5432)
            ok, error = _tcp_probe(host, port)
            checks["cloud_database_tcp"] = {
                "ok": ok,
                "detail": None if ok else error,
            }
            if not ok and status == "ok":
                status = "degraded"
            cloud_engine = None
            try:
                cloud_engine = create_engine(cloud_database_url)
                revision_check = _check_alembic_revision(
                    cloud_engine,
                    label="cloud",
                    database_url=cloud_database_url,
                    allow_auto_migration=str(
                        os.getenv("ENABLE_CLOUD_SYNC_AUTO_MIGRATION", "")
                    ).lower()
                    in {"1", "true", "yes", "on"},
                )
                checks["cloud_alembic_revision"] = revision_check
                if not revision_check["ok"]:
                    status = "error"
                if revision_check.get("detail") == "auto-migrated to heads":
                    cloud_engine.dispose()
                    cloud_engine = create_engine(cloud_database_url)
                cloud_inspector = sa_inspect(cloud_engine)
                receive_tables = set(cloud_inspector.get_table_names(schema="ops"))
                checks["cloud_receive_log_table"] = {
                    "ok": "cloud_sync_receive_log" in receive_tables,
                    "detail": None
                    if "cloud_sync_receive_log" in receive_tables
                    else "missing ops.cloud_sync_receive_log",
                }
                if not checks["cloud_receive_log_table"]["ok"]:
                    status = "error"
            except Exception as exc:
                checks["cloud_alembic_revision"] = {
                    "ok": False,
                    "detail": str(exc),
                }
                checks.setdefault(
                    "cloud_receive_log_table",
                    {
                        "ok": False,
                        "detail": str(exc),
                    },
                )
                status = "error"
            finally:
                if cloud_engine is not None:
                    cloud_engine.dispose()
        except Exception as exc:
            checks["cloud_database_url"] = {
                "ok": False,
                "detail": str(exc),
            }
            checks["cloud_database_tcp"] = {
                "ok": False,
                "detail": "cloud database url invalid",
            }
            checks["cloud_alembic_revision"] = {
                "ok": False,
                "detail": "cloud database url invalid",
            }
            checks["cloud_receive_log_table"] = {
                "ok": False,
                "detail": "cloud database url invalid",
            }
            status = "error"
    else:
        checks["cloud_database_url"] = {
            "ok": False,
            "detail": "missing",
        }
        checks["cloud_database_tcp"] = {
            "ok": False,
            "detail": "missing",
        }
        checks["cloud_alembic_revision"] = {
            "ok": False,
            "detail": "missing CLOUD_DATABASE_URL",
        }
        checks["cloud_receive_log_table"] = {
            "ok": False,
            "detail": "missing CLOUD_DATABASE_URL",
        }
        status = "degraded" if status == "ok" else status

    tunnel_enabled = str(os.getenv("CLOUD_SYNC_TUNNEL_ENABLED", "")).lower() in {"1", "true", "yes", "on"}
    tunnel_host = os.getenv("CLOUD_SYNC_TUNNEL_HOST")
    tunnel_port = os.getenv("CLOUD_SYNC_TUNNEL_PORT")
    if tunnel_enabled:
        if tunnel_host and tunnel_port:
            ok, error = _tcp_probe(tunnel_host, int(tunnel_port))
            checks["cloud_sync_tunnel"] = {
                "ok": ok,
                "detail": None if ok else error,
            }
            if not ok and status == "ok":
                status = "degraded"
        else:
            checks["cloud_sync_tunnel"] = {
                "ok": False,
                "detail": "missing host or port",
            }
            status = "degraded" if status == "ok" else status
    else:
        checks["cloud_sync_tunnel"] = {
            "ok": True,
            "detail": "disabled",
        }

    return {"status": status, "checks": checks}


def _build_cloud_sync_service(
    *,
    local_engine,
    cloud_engine,
    session_factory,
    dry_run: bool,
    checkpoint_scope: str,
) -> CloudBClassSyncService:
    checkpoint_service = CloudBClassSyncCheckpointService(session_factory())
    mirror_manager = NoOpCloudBClassMirrorManager() if dry_run else CloudBClassMirrorManager(cloud_engine)
    source_reader = SQLAlchemyBClassSourceReader(local_engine)
    cloud_writer = SQLAlchemyCloudWriter(cloud_engine, dry_run=dry_run)

    def inspect_tables():
        inspector = sa_inspect(local_engine)
        return inspector.get_table_names(schema="b_class")

    return CloudBClassSyncService(
        checkpoint_service=checkpoint_service,
        mirror_manager=mirror_manager,
        source_batch_reader=source_reader,
        remote_writer=cloud_writer,
        table_inspector=inspect_tables,
        local_engine=local_engine,
        cloud_engine=cloud_engine,
        owns_engines=False,
        checkpoint_scope=checkpoint_scope,
    )


def build_cloud_sync_service_from_env(dry_run: bool = False) -> CloudBClassSyncService:
    cloud_database_url = os.getenv("CLOUD_DATABASE_URL")
    if not dry_run and not cloud_database_url:
        raise RuntimeError("CLOUD_DATABASE_URL is required unless dry_run is enabled")

    local_engine = create_engine(DATABASE_URL)
    cloud_engine = create_engine(cloud_database_url) if cloud_database_url else local_engine
    checkpoint_scope = _build_checkpoint_scope_key(cloud_database_url, dry_run)

    service = _build_cloud_sync_service(
        local_engine=local_engine,
        cloud_engine=cloud_engine,
        session_factory=SessionLocal,
        dry_run=dry_run,
        checkpoint_scope=checkpoint_scope,
    )
    service.owns_engines = True
    return service


class CloudSyncWorkerFactory:
    def __init__(
        self,
        *,
        local_engine,
        cloud_engine,
        session_factory,
        dry_run: bool,
        batch_size: int = 1000,
    ) -> None:
        self.local_engine = local_engine
        self.cloud_engine = cloud_engine
        self.session_factory = session_factory
        self.dry_run = dry_run
        self.batch_size = batch_size
        self.checkpoint_scope = _build_checkpoint_scope_key(
            str(cloud_engine.url) if hasattr(cloud_engine, "url") else None,
            dry_run,
        )

    def __call__(self):
        db = self.session_factory()
        service = _build_cloud_sync_service(
            local_engine=self.local_engine,
            cloud_engine=self.cloud_engine,
            session_factory=self.session_factory,
            dry_run=self.dry_run,
            checkpoint_scope=self.checkpoint_scope,
        )
        return CloudBClassAutoSyncWorker(
            db=db,
            sync_executor=service,
            batch_size=self.batch_size,
            heartbeat_session_factory=self.session_factory,
        )

    def recover_stale_running_tasks(self, worker_id: str) -> dict:
        db = self.session_factory()
        now = datetime.now(timezone.utc)
        recovered: list[CloudBClassSyncTask] = []
        current_scope_recovered = 0
        legacy_scope_recovered = 0
        try:
            stmt = (
                select(CloudBClassSyncTask)
                .where(
                    CloudBClassSyncTask.status == "running",
                    CloudBClassSyncTask.lease_expires_at.is_not(None),
                    CloudBClassSyncTask.lease_expires_at < now,
                )
                .order_by(CloudBClassSyncTask.id.asc())
            )
            tasks = db.execute(stmt).scalars().all()
            for task in tasks:
                metadata = dict(task.metadata_json or {})
                task_scope = metadata.get("checkpoint_scope")
                is_current_scope = task_scope in {None, self.checkpoint_scope}

                task.status = "pending" if is_current_scope else "failed"
                task.claimed_by = None
                task.lease_expires_at = None
                task.heartbeat_at = None
                task.next_retry_at = None
                task.last_attempt_finished_at = now
                metadata["recovered_at"] = now.isoformat()
                if is_current_scope:
                    metadata["recovery_reason"] = "stale_running_recovered_on_startup"
                    task.last_error = None
                    task.error_code = None
                    current_scope_recovered += 1
                else:
                    metadata["recovery_reason"] = "legacy_scope_stale_recovered"
                    metadata["original_checkpoint_scope"] = task_scope
                    metadata["recovered_by_scope"] = self.checkpoint_scope
                    task.last_error = "legacy scope stale running task recovered"
                    task.error_code = "legacy_scope_stale_recovered"
                    legacy_scope_recovered += 1
                metadata["recovered_at"] = now.isoformat()
                task.metadata_json = metadata
                recovered.append(task)
            if recovered:
                db.commit()
                for task in recovered:
                    logger.warning(
                        "[CloudSyncRecovery] recovered stale running task job_id=%s table=%s reason=stale_running_recovered_on_startup worker_id=%s",
                        task.job_id,
                        task.source_table_name,
                        worker_id,
                    )
            else:
                db.rollback()
            return {
                "recovered_count": len(recovered),
                "recovered_current_scope_count": current_scope_recovered,
                "recovered_legacy_scope_count": legacy_scope_recovered,
            }
        finally:
            db.close()

    def close(self) -> None:
        try:
            self.local_engine.dispose()
        finally:
            if self.cloud_engine is not self.local_engine:
                self.cloud_engine.dispose()


def build_cloud_sync_worker_factory_from_env(dry_run: bool = False):
    cloud_database_url = os.getenv("CLOUD_DATABASE_URL")
    if not dry_run and not cloud_database_url:
        raise RuntimeError("CLOUD_DATABASE_URL is required unless dry_run is enabled")

    local_engine = create_engine(DATABASE_URL)
    cloud_engine = create_engine(cloud_database_url) if cloud_database_url else local_engine
    batch_size = int(os.getenv("CLOUD_SYNC_BATCH_SIZE", "1000"))

    return CloudSyncWorkerFactory(
        local_engine=local_engine,
        cloud_engine=cloud_engine,
        session_factory=SessionLocal,
        dry_run=dry_run,
        batch_size=batch_size,
    )


def build_cloud_sync_runtime_from_env(dry_run: bool = False):
    enabled_flag = os.getenv("CLOUD_SYNC_WORKER_ENABLED")
    enable_collection = os.getenv("ENABLE_COLLECTION", "true").lower() in {"true", "1", "yes", "on"}
    deployment_role = os.getenv("DEPLOYMENT_ROLE", "")

    if not should_enable_cloud_sync_worker(enabled_flag, enable_collection, deployment_role):
        return None

    worker_factory = build_cloud_sync_worker_factory_from_env(dry_run=dry_run)
    poll_interval_seconds = float(os.getenv("CLOUD_SYNC_POLL_INTERVAL_SECONDS", "5"))
    worker_id = os.getenv("CLOUD_SYNC_WORKER_ID", "cloud-sync-worker-1")

    return CloudBClassAutoSyncRuntime(
        worker_factory=worker_factory,
        poll_interval_seconds=poll_interval_seconds,
        worker_id=worker_id,
    )
