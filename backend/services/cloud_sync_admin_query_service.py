from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas.cloud_sync_admin import (
    CloudSyncCheckpointState,
    CloudSyncDependencyHealth,
    CloudSyncHealthSummary,
    CloudSyncLatestTaskState,
    CloudSyncProjectionState,
    CloudSyncQueueSummary,
    CloudSyncTableStateRow,
    CloudSyncTaskRow,
    CloudSyncWorkerHealth,
)
from modules.core.db import CloudBClassSyncCheckpoint, CloudBClassSyncTask


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


class CloudSyncAdminQueryService:
    def __init__(self, db: AsyncSession):
        self.db = db

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

        payload = CloudSyncHealthSummary(
            worker=CloudSyncWorkerHealth(
                status=(runtime_health or {}).get("status", "not_started"),
                worker_id=(runtime_health or {}).get("worker_id"),
                poll_interval_seconds=(runtime_health or {}).get("poll_interval_seconds"),
                last_error=_sanitize_error_text((runtime_health or {}).get("last_error")),
                last_heartbeat_at=(runtime_health or {}).get("last_heartbeat_at"),
            ),
            tunnel=CloudSyncDependencyHealth(status="unknown"),
            cloud_db=CloudSyncDependencyHealth(status="unknown"),
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

    def _serialize_task(self, task: CloudBClassSyncTask) -> CloudSyncTaskRow:
        return CloudSyncTaskRow(
            job_id=task.job_id,
            status=task.status,
            source_table_name=task.source_table_name,
            attempt_count=int(task.attempt_count or 0),
            trigger_source=task.trigger_source,
            source_file_id=task.source_file_id,
            claimed_by=task.claimed_by,
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
