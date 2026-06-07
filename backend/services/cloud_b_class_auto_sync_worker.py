from __future__ import annotations

import asyncio
import inspect
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

from backend.services.task_center_sync_service import TaskCenterSyncService
from modules.core.db import CloudBClassSyncRun, CloudBClassSyncTask, SystemConfig


class CloudBClassAutoSyncWorker:
    """Claim and execute automatic cloud-sync tasks."""

    MAX_RETRY_ATTEMPTS = 4
    RETRYABLE_ERROR_CODES = {
        "cloud_db_unavailable",
        "tunnel_unhealthy",
        "ssh_process_failed",
        "projection_runtime_failure",
    }

    def __init__(self, db, sync_executor, lease_seconds: int = 300, batch_size: int = 1000):
        self.db = db
        self.sync_executor = sync_executor
        self.lease_seconds = lease_seconds
        self.batch_size = batch_size

    def _auto_sync_enabled(self) -> bool:
        explicit_flag = os.getenv("CLOUD_SYNC_AUTO_SYNC_ENABLED")
        if explicit_flag is not None:
            return str(explicit_flag).lower() in {"1", "true", "yes", "on"}
        try:
            stmt = select(SystemConfig).where(SystemConfig.config_key == "cloud_sync_auto_sync_enabled")
            record = self.db.execute(stmt).scalars().one_or_none()
            if record is not None:
                return str(record.config_value).lower() in {"1", "true", "yes", "on"}
        except Exception:
            pass
        return True

    def claim_next_task(self, worker_id: str) -> CloudBClassSyncTask | None:
        if not self._auto_sync_enabled():
            return None

        task_center = TaskCenterSyncService(self.db)
        now = datetime.now(timezone.utc)
        stmt = (
            select(CloudBClassSyncTask)
            .where(
                or_(
                    CloudBClassSyncTask.status == "pending",
                    (
                        CloudBClassSyncTask.status == "retry_waiting"
                    )
                    & (
                        CloudBClassSyncTask.next_retry_at.is_(None)
                    )
                    | (
                        (CloudBClassSyncTask.status == "retry_waiting")
                        & (CloudBClassSyncTask.next_retry_at.is_not(None))
                        & (CloudBClassSyncTask.next_retry_at <= now)
                    ),
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
        mirrored = task_center.get_task(task.job_id)
        if mirrored is not None:
            task_center.update_task(
                mirrored,
                status="running",
                claimed_by=worker_id,
                heartbeat_at=task.heartbeat_at,
                lease_expires_at=task.lease_expires_at,
                attempt_count=task.attempt_count,
            )
        return task

    def heartbeat(self, task_id: int, worker_id: str) -> None:
        task_center = TaskCenterSyncService(self.db)
        task = self.db.get(CloudBClassSyncTask, task_id)
        if task is None or task.claimed_by != worker_id:
            return
        now = datetime.now(timezone.utc)
        task.heartbeat_at = now
        task.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
        self.db.commit()
        mirrored = task_center.get_task(task.job_id)
        if mirrored is not None:
            task_center.update_task(
                mirrored,
                heartbeat_at=task.heartbeat_at,
                lease_expires_at=task.lease_expires_at,
            )

    async def _maybe_await(self, value):
        if inspect.isawaitable(value):
            return await value
        return value

    async def _run_with_lease_heartbeat(self, task_id: int, worker_id: str, operation):
        if not inspect.isawaitable(operation):
            return operation

        stop_event = asyncio.Event()

        async def _heartbeat_loop() -> None:
            interval_seconds = max(float(self.lease_seconds) / 2.0, 0.05)
            while not stop_event.is_set():
                try:
                    await asyncio.sleep(interval_seconds)
                    if stop_event.is_set():
                        break
                    self.heartbeat(task_id, worker_id)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    break

        heartbeat_task = asyncio.create_task(_heartbeat_loop())
        try:
            return await operation
        finally:
            stop_event.set()
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

    @staticmethod
    def _result_error_code(result: dict) -> str:
        return (
            result.get("error_code")
            or result.get("error")
            or result.get("detail")
            or "sync_failed"
        )

    async def run_one(self, worker_id: str) -> CloudBClassSyncTask | None:
        task_center = TaskCenterSyncService(self.db)
        task = self.claim_next_task(worker_id=worker_id)
        if task is None:
            return None

        try:
            result = await self._run_with_lease_heartbeat(
                task.id,
                worker_id,
                self.sync_executor.sync_table(task.source_table_name, batch_size=self.batch_size),
            )
            sync_status = result.get("status", "completed")
            projection_status = result.get("projection_status", "completed")
            if sync_status != "completed":
                task.status = "failed"
                task.projection_status = projection_status
                task.last_error = result.get("error") or result.get("detail") or "sync_failed"
                task.error_code = self._result_error_code(result)
                task.next_retry_at = None
            else:
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
            if (
                error_code in self.RETRYABLE_ERROR_CODES
                and int(task.attempt_count or 0) <= self.MAX_RETRY_ATTEMPTS
            ):
                task.status = "retry_waiting"
                task.next_retry_at = self._compute_next_retry_at(task.attempt_count, error_code)
            else:
                task.status = "failed"
                task.next_retry_at = None
        finally:
            task.last_attempt_finished_at = datetime.now(timezone.utc)
            if task.status in {"completed", "partial_success", "failed"}:
                task.finished_at = task.last_attempt_finished_at
            task.lease_expires_at = None
            self.db.commit()
            self.db.refresh(task)
            self._update_parent_run(task)
            mirrored = task_center.get_task(task.job_id)
            if mirrored is not None:
                task_center.update_task(
                    mirrored,
                    status=task.status,
                    claimed_by=task.claimed_by,
                    heartbeat_at=task.heartbeat_at,
                    lease_expires_at=task.lease_expires_at,
                    next_retry_at=task.next_retry_at,
                    error_summary=task.last_error,
                    finished_at=task.finished_at or task.last_attempt_finished_at,
                    details_json={
                        "cloud_sync": {
                            "error_code": task.error_code,
                            "projection_status": task.projection_status,
                            "attempt_count": task.attempt_count,
                        }
                    },
                )

        return task

    def _update_parent_run(self, task: CloudBClassSyncTask) -> None:
        run_id = (task.metadata_json or {}).get("run_id")
        if not run_id:
            return

        run = self.db.get(CloudBClassSyncRun, run_id)
        if run is None:
            return

        all_tasks = self.db.execute(select(CloudBClassSyncTask)).scalars().all()
        run_tasks = [
            item
            for item in all_tasks
            if (item.metadata_json or {}).get("run_id") == run_id
        ]
        if not run_tasks:
            return

        terminal_statuses = {"completed", "partial_success", "failed", "cancelled"}
        failed_statuses = {"failed", "partial_success"}
        succeeded_count = sum(1 for item in run_tasks if item.status == "completed")
        failed_count = sum(1 for item in run_tasks if item.status in failed_statuses)
        active_count = sum(1 for item in run_tasks if item.status not in terminal_statuses)

        run.succeeded_tables = succeeded_count
        run.failed_tables = failed_count
        if active_count:
            run.status = "running"
            run.finished_at = None
        else:
            run.finished_at = datetime.now(timezone.utc)
            if failed_count == 0:
                run.status = "completed"
                run.error_summary = None
            elif succeeded_count:
                run.status = "partial_success"
                run.error_summary = f"{failed_count} tables failed or partially succeeded"
            else:
                run.status = "failed"
                run.error_summary = f"{failed_count} tables failed"
        self.db.commit()

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
