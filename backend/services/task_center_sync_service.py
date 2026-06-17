from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy import select
from sqlalchemy.orm import Session

from modules.core.db import TaskCenterLink, TaskCenterLog, TaskCenterTask


class TaskCenterSyncService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _is_missing_table_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return (
            'relation "task_center_tasks" does not exist' in message
            or "no such table: task_center_tasks" in message
            or 'relation "task_center_logs" does not exist' in message
            or "no such table: task_center_logs" in message
            or 'relation "task_center_links" does not exist' in message
            or "no such table: task_center_links" in message
        )

    def get_task(self, task_id: str) -> TaskCenterTask | None:
        try:
            return self.db.execute(
                select(TaskCenterTask).where(TaskCenterTask.task_id == task_id)
            ).scalar_one_or_none()
        except (OperationalError, ProgrammingError) as exc:
            if not self._is_missing_table_error(exc):
                raise
            self.db.rollback()
            return None

    def create_task(self, **fields: Any) -> TaskCenterTask:
        task = TaskCenterTask(**fields)
        try:
            self.db.add(task)
            self.db.commit()
            self.db.refresh(task)
        except (OperationalError, ProgrammingError) as exc:
            if not self._is_missing_table_error(exc):
                raise
            self.db.rollback()
        return task

    def update_task(self, task: TaskCenterTask, **updates: Any) -> TaskCenterTask:
        try:
            for key, value in updates.items():
                if hasattr(task, key):
                    setattr(task, key, value)
            task.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(task)
        except (OperationalError, ProgrammingError) as exc:
            if not self._is_missing_table_error(exc):
                raise
            self.db.rollback()
        return task

    def sync_cloud_task(self, cloud_task) -> TaskCenterTask | None:
        details = dict(getattr(cloud_task, "metadata_json", {}) or {})
        cloud_sync_details = {
            "metadata": details,
            "projection_preset": getattr(cloud_task, "projection_preset", None),
            "projection_status": getattr(cloud_task, "projection_status", None),
            "error_code": getattr(cloud_task, "error_code", None),
            "attempt_count": int(getattr(cloud_task, "attempt_count", 0) or 0),
        }

        mirrored = self.get_task(getattr(cloud_task, "job_id"))
        payload = {
            "status": getattr(cloud_task, "status", None),
            "trigger_source": getattr(cloud_task, "trigger_source", None),
            "platform_code": getattr(cloud_task, "platform_code", None),
            "source_file_id": getattr(cloud_task, "source_file_id", None),
            "source_table_name": getattr(cloud_task, "source_table_name", None),
            "claimed_by": getattr(cloud_task, "claimed_by", None),
            "heartbeat_at": getattr(cloud_task, "heartbeat_at", None),
            "lease_expires_at": getattr(cloud_task, "lease_expires_at", None),
            "next_retry_at": getattr(cloud_task, "next_retry_at", None),
            "attempt_count": int(getattr(cloud_task, "attempt_count", 0) or 0),
            "started_at": getattr(cloud_task, "last_attempt_started_at", None),
            "finished_at": getattr(cloud_task, "finished_at", None) or getattr(cloud_task, "last_attempt_finished_at", None),
            "error_summary": getattr(cloud_task, "last_error", None),
            "details_json": {"cloud_sync": cloud_sync_details},
        }
        if mirrored is not None:
            return self.update_task(mirrored, **payload)

        return self.create_task(
            task_id=getattr(cloud_task, "job_id"),
            task_family="cloud_sync",
            task_type="auto_sync",
            created_at=getattr(cloud_task, "created_at", None) or datetime.now(timezone.utc),
            **payload,
        )

    def append_log(
        self,
        task_id: str,
        *,
        level: str,
        event_type: str,
        message: str,
        details_json: dict[str, Any] | None = None,
    ) -> TaskCenterLog | None:
        task = self.get_task(task_id)
        if task is None:
            return None
        log = TaskCenterLog(
            task_pk=task.id,
            level=level,
            event_type=event_type,
            message=message,
            details_json=details_json,
        )
        try:
            self.db.add(log)
            self.db.commit()
            self.db.refresh(log)
            return log
        except (OperationalError, ProgrammingError) as exc:
            if not self._is_missing_table_error(exc):
                raise
            self.db.rollback()
            return None

    def add_link(
        self,
        task_id: str,
        *,
        subject_type: str,
        subject_id: str | None = None,
        subject_key: str | None = None,
        details_json: dict[str, Any] | None = None,
    ) -> TaskCenterLink | None:
        task = self.get_task(task_id)
        if task is None:
            return None
        link = TaskCenterLink(
            task_pk=task.id,
            subject_type=subject_type,
            subject_id=subject_id,
            subject_key=subject_key,
            details_json=details_json,
        )
        try:
            self.db.add(link)
            self.db.commit()
            self.db.refresh(link)
            return link
        except (OperationalError, ProgrammingError) as exc:
            if not self._is_missing_table_error(exc):
                raise
            self.db.rollback()
            return None
