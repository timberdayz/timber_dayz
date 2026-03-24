from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

from modules.core.db import CloudBClassSyncTask


class CloudBClassAutoSyncWorker:
    """Claim and execute automatic cloud-sync tasks."""

    RETRYABLE_ERROR_CODES = {
        "cloud_db_unavailable",
        "tunnel_unhealthy",
        "ssh_process_failed",
        "projection_runtime_failure",
    }

    def __init__(self, db, sync_executor, lease_seconds: int = 300):
        self.db = db
        self.sync_executor = sync_executor
        self.lease_seconds = lease_seconds

    def claim_next_task(self, worker_id: str) -> CloudBClassSyncTask | None:
        now = datetime.now(timezone.utc)
        stmt = (
            select(CloudBClassSyncTask)
            .where(
                or_(
                    CloudBClassSyncTask.status.in_(("pending", "retry_waiting")),
                    (
                        CloudBClassSyncTask.status == "running"
                    )
                    & (
                        CloudBClassSyncTask.lease_expires_at.is_not(None)
                    )
                    & (CloudBClassSyncTask.lease_expires_at < now),
                )
            )
            .order_by(CloudBClassSyncTask.id.asc())
        )
        task = self.db.execute(stmt).scalars().first()
        if task is None:
            return None

        task.status = "running"
        task.claimed_by = worker_id
        task.heartbeat_at = now
        task.last_attempt_started_at = now
        task.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
        task.attempt_count = int(task.attempt_count or 0) + 1
        self.db.commit()
        self.db.refresh(task)
        return task

    def heartbeat(self, task_id: int, worker_id: str) -> None:
        task = self.db.get(CloudBClassSyncTask, task_id)
        if task is None or task.claimed_by != worker_id:
            return
        now = datetime.now(timezone.utc)
        task.heartbeat_at = now
        task.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
        self.db.commit()

    async def _maybe_await(self, value):
        if inspect.isawaitable(value):
            return await value
        return value

    async def run_one(self, worker_id: str) -> CloudBClassSyncTask | None:
        task = self.claim_next_task(worker_id=worker_id)
        if task is None:
            return None

        try:
            result = await self._maybe_await(
                self.sync_executor.sync_table(task.source_table_name)
            )
            projection_status = result.get("projection_status", "completed")
            final_status = "completed" if projection_status == "completed" else "partial_success"
            task.status = final_status
            task.projection_status = projection_status
            task.last_error = None
            task.error_code = None
            task.next_retry_at = None
        except Exception as exc:
            error_code = str(exc)
            task.last_error = str(exc)
            task.error_code = error_code
            if error_code in self.RETRYABLE_ERROR_CODES:
                task.status = "retry_waiting"
                task.next_retry_at = self._compute_next_retry_at(task.attempt_count, error_code)
            else:
                task.status = "failed"
                task.next_retry_at = None
        finally:
            task.last_attempt_finished_at = datetime.now(timezone.utc)
            task.lease_expires_at = None
            self.db.commit()
            self.db.refresh(task)

        return task

    @staticmethod
    def _compute_next_retry_at(attempt_count: int, error_code: str) -> datetime:
        delay_minutes = {
            1: 1,
            2: 5,
            3: 15,
            4: 60,
        }.get(attempt_count, 60)
        return datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)

    def close(self) -> None:
        try:
            if hasattr(self.sync_executor, "close"):
                self.sync_executor.close()
        finally:
            try:
                self.db.close()
            except Exception:
                pass
