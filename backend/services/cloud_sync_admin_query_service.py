from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
import socket
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.engine import make_url

from backend.schemas.cloud_sync_admin import (
    CloudSyncCheckpointState,
    CloudSyncDependencyHealth,
    CloudSyncHealthSummary,
    CloudSyncHistoryRow,
    CloudSyncLatestTaskState,
    CloudSyncOverviewSummary,
    CloudSyncProjectionState,
    CloudSyncQueueSummary,
    CloudSyncRuntimeSummary,
    CloudSyncSettings,
    CloudSyncTableStateRow,
    CloudSyncTaskRow,
    CloudSyncWorkerHealth,
)
from modules.core.db import CloudBClassSyncCheckpoint, CloudBClassSyncTask, SystemConfig


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _sanitize_error_text(value: str | None) -> str | None:
    if not value:
        return value

    sanitized = re.sub(r'://([^:/\s]+):([^@/\s]+)@', r'://\1:***@', value)
    sanitized = re.sub(r'(?i)\b(password|secret|token)=([^\s&]+)', r'\1=***', sanitized)
    return sanitized


def _probe_tcp_target(host: str, port: int, timeout_seconds: float = 1.0) -> tuple[bool, str | None]:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True, None
    except Exception as exc:
        return False, _sanitize_error_text(str(exc))


class CloudSyncAdminQueryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _parse_bool(value: str | None, default: bool = True) -> bool:
        if value is None:
            return default
        return str(value).lower() in {"1", "true", "yes", "on"}

    async def _auto_sync_enabled(self) -> bool:
        try:
            result = await self.db.execute(
                select(SystemConfig).where(SystemConfig.config_key == "cloud_sync_auto_sync_enabled")
            )
            record = result.scalars().one_or_none()
            if record is not None:
                return self._parse_bool(record.config_value, default=True)
        except Exception:
            pass

        return self._parse_bool(os.getenv("CLOUD_SYNC_AUTO_SYNC_ENABLED", "true"), default=True)

    async def get_health_summary(self, runtime_health: dict | None = None) -> dict:
        tasks = (await self.db.execute(select(CloudBClassSyncTask))).scalars().all()
        now = datetime.now(timezone.utc)
        oldest_pending = min(
            (
                int((now - _as_utc(task.created_at)).total_seconds())
                for task in tasks
                if task.status in {"pending", "retry_waiting"} and task.created_at is not None
            ),
            default=None,
        )
        completed_recent_24h = sum(
            1
            for task in tasks
            if task.status == "completed"
            and task.finished_at is not None
            and _as_utc(task.finished_at) >= now - timedelta(hours=24)
        )

        cloud_db_health = self._probe_cloud_db_health()
        tunnel_health = self._probe_tunnel_health(cloud_db_health)

        payload = CloudSyncHealthSummary(
            worker=CloudSyncWorkerHealth(
                status=(runtime_health or {}).get("status", "not_started"),
                worker_id=(runtime_health or {}).get("worker_id"),
                poll_interval_seconds=(runtime_health or {}).get("poll_interval_seconds"),
                last_error=_sanitize_error_text((runtime_health or {}).get("last_error")),
                last_heartbeat_at=(runtime_health or {}).get("last_heartbeat_at"),
            ),
            tunnel=CloudSyncDependencyHealth(**tunnel_health),
            cloud_db=CloudSyncDependencyHealth(**cloud_db_health),
            queue=CloudSyncQueueSummary(
                pending=sum(1 for task in tasks if task.status == "pending"),
                running=sum(1 for task in tasks if task.status == "running"),
                retry_waiting=sum(1 for task in tasks if task.status == "retry_waiting"),
                failed=sum(1 for task in tasks if task.status == "failed"),
                partial_success=sum(1 for task in tasks if task.status == "partial_success"),
                completed_recent_24h=completed_recent_24h,
                oldest_pending_age_seconds=oldest_pending,
            ),
        )
        return payload.model_dump()

    async def list_tasks(self, *, limit: int = 100) -> list[dict]:
        stmt = select(CloudBClassSyncTask).order_by(CloudBClassSyncTask.id.desc()).limit(limit)
        tasks = (await self.db.execute(stmt)).scalars().all()
        return [self._serialize_task(task).model_dump() for task in tasks]

    async def get_task(self, job_id: str) -> dict | None:
        stmt = select(CloudBClassSyncTask).where(CloudBClassSyncTask.job_id == job_id)
        task = (await self.db.execute(stmt)).scalars().one_or_none()
        if task is None:
            return None
        return self._serialize_task(task).model_dump()

    async def list_table_states(self) -> list[dict]:
        checkpoints = (
            await self.db.execute(select(CloudBClassSyncCheckpoint).order_by(CloudBClassSyncCheckpoint.id.desc()))
        ).scalars().all()
        tasks = (
            await self.db.execute(select(CloudBClassSyncTask).order_by(CloudBClassSyncTask.id.desc()))
        ).scalars().all()

        checkpoint_by_table = {}
        for checkpoint in checkpoints:
            checkpoint_by_table.setdefault(checkpoint.table_name, checkpoint)

        latest_task_by_table = {}
        for task in tasks:
            latest_task_by_table.setdefault(task.source_table_name, task)

        table_names = sorted(set(checkpoint_by_table) | set(latest_task_by_table))
        rows = []
        for table_name in table_names:
            checkpoint = checkpoint_by_table.get(table_name)
            latest_task = latest_task_by_table.get(table_name)
            row = CloudSyncTableStateRow(
                source_table_name=table_name,
                platform_code=getattr(latest_task, "platform_code", None),
                data_domain=getattr(latest_task, "data_domain", None),
                sub_domain=getattr(latest_task, "sub_domain", None),
                checkpoint=CloudSyncCheckpointState(
                    table_schema=getattr(checkpoint, "table_schema", None),
                    last_source_id=getattr(checkpoint, "last_source_id", None),
                    last_ingest_timestamp=_iso(getattr(checkpoint, "last_ingest_timestamp", None)),
                    last_status=getattr(checkpoint, "last_status", None),
                    last_error=_sanitize_error_text(getattr(checkpoint, "last_error", None)),
                ),
                latest_task=self._serialize_task_state(latest_task),
                projection=CloudSyncProjectionState(
                    preset=getattr(latest_task, "projection_preset", None),
                    status=getattr(latest_task, "projection_status", None),
                ),
                last_success_at=_iso(getattr(latest_task, "finished_at", None))
                if getattr(latest_task, "status", None) == "completed"
                else None,
                latest_error=_sanitize_error_text(
                    getattr(latest_task, "last_error", None) or getattr(checkpoint, "last_error", None)
                ),
            )
            rows.append(row.model_dump())
        return rows

    async def list_events(self, *, limit: int = 20) -> list[dict]:
        stmt = select(CloudBClassSyncTask).order_by(CloudBClassSyncTask.id.desc()).limit(limit)
        tasks = (await self.db.execute(stmt)).scalars().all()
        events = []
        for task in tasks:
            timestamp = task.last_attempt_finished_at or task.last_attempt_started_at or task.created_at
            events.append(
                {
                    "title": f"{task.source_table_name} {task.status}",
                    "status": task.status,
                    "job_id": task.job_id,
                    "source_table_name": task.source_table_name,
                    "timestamp": _iso(timestamp),
                    "last_error": _sanitize_error_text(task.last_error),
                }
            )
        return events

    async def get_overview_summary(self, runtime_health: dict | None = None) -> dict:
        tasks = (await self.db.execute(select(CloudBClassSyncTask).order_by(CloudBClassSyncTask.id.desc()))).scalars().all()
        failed = sum(1 for task in tasks if task.status == "failed")
        partial_success = sum(1 for task in tasks if task.status == "partial_success")
        pending = sum(1 for task in tasks if task.status == "pending")
        running = sum(1 for task in tasks if task.status == "running")
        retry_waiting = sum(1 for task in tasks if task.status == "retry_waiting")
        latest_success = next((task for task in tasks if task.status == "completed" and task.finished_at is not None), None)
        latest_error_task = next((task for task in tasks if task.last_error), None)

        if failed or partial_success:
            catch_up_status = "degraded"
        elif running:
            catch_up_status = "catching_up"
        elif pending or retry_waiting:
            catch_up_status = "backlog"
        else:
            catch_up_status = "up_to_date"

        payload = CloudSyncOverviewSummary(
            worker_status=(runtime_health or {}).get("status", "not_started"),
            catch_up_status=catch_up_status,
            exception_task_count=failed + partial_success,
            failed_task_count=failed,
            partial_success_task_count=partial_success,
            pending_task_count=pending,
            running_task_count=running,
            retry_waiting_task_count=retry_waiting,
            last_success_at=_iso(getattr(latest_success, "finished_at", None)),
            latest_error=_sanitize_error_text(getattr(latest_error_task, "last_error", None)),
            auto_sync_enabled=await self._auto_sync_enabled(),
        )
        return payload.model_dump()

    async def get_runtime_summary(self, runtime_health: dict | None = None) -> dict:
        running_task = (
            await self.db.execute(
                select(CloudBClassSyncTask)
                .where(CloudBClassSyncTask.status == "running")
                .order_by(CloudBClassSyncTask.id.desc())
            )
        ).scalars().first()
        active_count = len(
            (
                await self.db.execute(
                    select(CloudBClassSyncTask).where(CloudBClassSyncTask.status == "running")
                )
            ).scalars().all()
        )
        payload = CloudSyncRuntimeSummary(
            worker_status=(runtime_health or {}).get("status", "not_started"),
            worker_id=(runtime_health or {}).get("worker_id"),
            is_running=active_count > 0,
            active_task_count=active_count,
            current_job_id=getattr(running_task, "job_id", None),
            current_source_table_name=getattr(running_task, "source_table_name", None),
            last_heartbeat_at=(runtime_health or {}).get("last_heartbeat_at"),
            last_error=_sanitize_error_text((runtime_health or {}).get("last_error")),
        )
        return payload.model_dump()

    async def list_history(self, *, limit: int = 20) -> list[dict]:
        tasks = (
            await self.db.execute(select(CloudBClassSyncTask).order_by(CloudBClassSyncTask.id.desc()).limit(limit))
        ).scalars().all()
        return [
            CloudSyncHistoryRow(
                job_id=task.job_id,
                source_table_name=task.source_table_name,
                trigger_source=task.trigger_source,
                result_status=task.status,
                started_at=_iso(task.last_attempt_started_at),
                finished_at=_iso(task.last_attempt_finished_at or task.finished_at),
                last_error=_sanitize_error_text(task.last_error),
            ).model_dump()
            for task in tasks
        ]

    async def get_settings(self) -> dict:
        return CloudSyncSettings(
            auto_sync_enabled=await self._auto_sync_enabled(),
            pause_mode="buffer_backlog",
        ).model_dump()

    def _serialize_task(self, task: CloudBClassSyncTask) -> CloudSyncTaskRow:
        return CloudSyncTaskRow(
            job_id=task.job_id,
            status=task.status,
            source_table_name=task.source_table_name,
            attempt_count=int(task.attempt_count or 0),
            trigger_source=task.trigger_source,
            source_file_id=task.source_file_id,
            claimed_by=task.claimed_by,
            next_retry_at=_iso(task.next_retry_at),
            lease_expires_at=_iso(task.lease_expires_at),
            heartbeat_at=_iso(task.heartbeat_at),
            last_attempt_started_at=_iso(task.last_attempt_started_at),
            last_attempt_finished_at=_iso(task.last_attempt_finished_at),
            projection_status=task.projection_status,
            projection_preset=task.projection_preset,
            last_error=_sanitize_error_text(task.last_error),
            error_code=task.error_code,
            created_at=_iso(task.created_at),
            updated_at=_iso(task.updated_at),
            finished_at=_iso(task.finished_at),
            metadata=task.metadata_json or {},
        )

    def _serialize_task_state(self, task: CloudBClassSyncTask | None) -> CloudSyncLatestTaskState:
        if task is None:
            return CloudSyncLatestTaskState()
        return CloudSyncLatestTaskState(**self._serialize_task(task).model_dump())

    def _probe_cloud_db_health(self) -> dict:
        cloud_database_url = os.getenv("CLOUD_DATABASE_URL")
        if not cloud_database_url:
            return {
                "status": "unknown",
                "last_checked_at": _iso(datetime.now(timezone.utc)),
                "error": None,
            }

        try:
            parsed = make_url(cloud_database_url)
            host = parsed.host or "127.0.0.1"
            port = int(parsed.port or 5432)
        except Exception as exc:
            return {
                "status": "unreachable",
                "last_checked_at": _iso(datetime.now(timezone.utc)),
                "error": _sanitize_error_text(str(exc)),
            }

        ok, error = _probe_tcp_target(host, port)
        return {
            "status": "reachable" if ok else "unreachable",
            "last_checked_at": _iso(datetime.now(timezone.utc)),
            "error": error,
        }

    def _probe_tunnel_health(self, cloud_db_health: dict) -> dict:
        tunnel_enabled = str(os.getenv("CLOUD_SYNC_TUNNEL_ENABLED", "")).lower() in {"1", "true", "yes", "on"}
        tunnel_host = os.getenv("CLOUD_SYNC_TUNNEL_HOST")
        tunnel_port = os.getenv("CLOUD_SYNC_TUNNEL_PORT")
        cloud_database_url = os.getenv("CLOUD_DATABASE_URL")

        if tunnel_enabled and tunnel_host and tunnel_port:
            ok, error = _probe_tcp_target(tunnel_host, int(tunnel_port))
            return {
                "status": "healthy" if ok else "unhealthy",
                "last_checked_at": _iso(datetime.now(timezone.utc)),
                "error": error,
            }

        if cloud_database_url:
            try:
                parsed = make_url(cloud_database_url)
                if (parsed.host or "").lower() in {"127.0.0.1", "localhost"}:
                    return {
                        "status": "healthy" if cloud_db_health["status"] == "reachable" else "unhealthy",
                        "last_checked_at": _iso(datetime.now(timezone.utc)),
                        "error": cloud_db_health.get("error"),
                    }
            except Exception:
                pass

        return {
            "status": "unknown",
            "last_checked_at": _iso(datetime.now(timezone.utc)),
            "error": None,
        }
