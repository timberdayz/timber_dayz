from __future__ import annotations

import asyncio
import inspect
import os
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

from backend.services.task_center_sync_service import TaskCenterSyncService
from modules.core.db import CloudBClassSyncRun, CloudBClassSyncTask, SystemConfig


class CloudBClassAutoSyncWorker:
    """Claim and execute automatic cloud-sync tasks."""

    MAX_RETRY_ATTEMPTS = 4
    RETRYABLE_ERROR_CODES = {
        "cloud_db_unavailable",
        "cloud_db_connection_closed",
        "tunnel_unhealthy",
        "ssh_process_failed",
        "projection_runtime_failure",
    }

    def __init__(
        self,
        db,
        sync_executor,
        lease_seconds: int = 300,
        batch_size: int = 1000,
        heartbeat_session_factory=None,
    ):
        self.db = db
        self.sync_executor = sync_executor
        self.lease_seconds = lease_seconds
        self.batch_size = batch_size
        self.heartbeat_session_factory = heartbeat_session_factory

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

    def _heartbeat_with_dedicated_session(self, task_id: int, worker_id: str) -> None:
        if self.heartbeat_session_factory is None:
            self.heartbeat(task_id, worker_id)
            return

        db = self.heartbeat_session_factory()
        try:
            task_center = TaskCenterSyncService(db)
            task = db.get(CloudBClassSyncTask, task_id)
            if task is None or task.claimed_by != worker_id:
                return
            now = datetime.now(timezone.utc)
            task.heartbeat_at = now
            task.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
            db.commit()
            mirrored = task_center.get_task(task.job_id)
            if mirrored is not None:
                task_center.update_task(
                    mirrored,
                    heartbeat_at=task.heartbeat_at,
                    lease_expires_at=task.lease_expires_at,
                )
        finally:
            db.close()

    def _heartbeat_interval_seconds(self) -> float:
        configured = os.getenv("CLOUD_SYNC_HEARTBEAT_INTERVAL_SECONDS")
        if configured:
            try:
                return max(float(configured), 0.05)
            except ValueError:
                pass
        return max(float(self.lease_seconds) / 2.0, 0.05)

    async def _run_with_lease_heartbeat(self, task_id: int, worker_id: str, operation_factory):
        stop_event = threading.Event()

        def _heartbeat_loop() -> None:
            interval_seconds = self._heartbeat_interval_seconds()
            while not stop_event.wait(interval_seconds):
                try:
                    self._heartbeat_with_dedicated_session(task_id, worker_id)
                except Exception:
                    break

        heartbeat_thread = threading.Thread(
            target=_heartbeat_loop,
            name=f"cloud-sync-heartbeat-{task_id}",
            daemon=True,
        )
        heartbeat_thread.start()
        try:
            operation = operation_factory()
            if not inspect.isawaitable(operation):
                return operation
            return await operation
        finally:
            stop_event.set()
            heartbeat_thread.join(timeout=max(self._heartbeat_interval_seconds(), 0.1))

    @staticmethod
    def _result_error_code(result: dict) -> str:
        return CloudBClassAutoSyncWorker._normalize_error_code(
            result.get("error_code")
            or result.get("error")
            or result.get("detail")
            or "sync_failed"
        )

    @staticmethod
    def _normalize_error_code(raw_error: object) -> str:
        message = str(raw_error or "sync_failed")
        lowered = message.lower()
        if "server closed the connection unexpectedly" in lowered or "could not receive data from server" in lowered:
            return "cloud_db_connection_closed"
        if "connection refused" in lowered or "timed out" in lowered or "timeout" in lowered:
            return "cloud_db_unavailable"
        if "software caused connection abort" in lowered:
            return "local_db_connection_aborted"
        if message in CloudBClassAutoSyncWorker.RETRYABLE_ERROR_CODES:
            return message
        if len(message) <= 64:
            return message
        return "sync_failed"

    def _is_retryable_error(self, error_code: str | None) -> bool:
        return str(error_code or "") in self.RETRYABLE_ERROR_CODES

    async def run_one(self, worker_id: str) -> CloudBClassSyncTask | None:
        task_center = TaskCenterSyncService(self.db)
        task = self.claim_next_task(worker_id=worker_id)
        if task is None:
            return None
        task_id = task.id
        source_table_name = task.source_table_name

        # Release the local DB connection before long cloud writes. Otherwise the
        # task session can sit idle for minutes and be closed before final status
        # commit, especially on Windows collection laptops.
        self.db.close()

        try:
            result = await self._run_with_lease_heartbeat(
                task_id,
                worker_id,
                lambda: self.sync_executor.sync_table(source_table_name, batch_size=self.batch_size),
            )
            task = self.db.get(CloudBClassSyncTask, task_id)
            if task is None:
                return None
            sync_status = result.get("status", "completed")
            projection_status = result.get("projection_status", "completed")
            if sync_status != "completed":
                task.projection_status = projection_status
                task.last_error = result.get("error") or result.get("detail") or "sync_failed"
                task.error_code = self._result_error_code(result)
                if (
                    self._is_retryable_error(task.error_code)
                    and int(task.attempt_count or 0) <= self.MAX_RETRY_ATTEMPTS
                ):
                    task.status = "retry_waiting"
                    task.next_retry_at = self._compute_next_retry_at(task.attempt_count, task.error_code)
                else:
                    task.status = "failed"
                    task.next_retry_at = None
            else:
                projection_terminal_success = {"completed", "queued", "not_required"}
                final_status = "completed" if projection_status in projection_terminal_success else "partial_success"
                task.status = final_status
                task.projection_status = projection_status
                task.last_error = None if final_status == "completed" else (
                    result.get("projection_error")
                    or result.get("error")
                    or result.get("detail")
                    or "projection_failed"
                )
                task.error_code = None if final_status == "completed" else self._result_error_code(result)
                task.next_retry_at = None
        except Exception as exc:
            task = self.db.get(CloudBClassSyncTask, task_id)
            if task is None:
                return None
            error_code = self._normalize_error_code(exc)
            task.last_error = str(exc)
            task.error_code = error_code
            if (
                self._is_retryable_error(error_code)
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
