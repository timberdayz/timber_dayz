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

    def get_task(self, task_id: str) -> TaskCenterTask | None:
        try:
            return self.db.execute(
                select(TaskCenterTask).where(TaskCenterTask.task_id == task_id)
            ).scalar_one_or_none()
        except (OperationalError, ProgrammingError):
            self.db.rollback()
            return None

    def create_task(self, **fields: Any) -> TaskCenterTask:
        task = TaskCenterTask(**fields)
        try:
            self.db.add(task)
            self.db.commit()
            self.db.refresh(task)
        except (OperationalError, ProgrammingError):
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
        except (OperationalError, ProgrammingError):
            self.db.rollback()
        return task

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
        except (OperationalError, ProgrammingError):
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
        except (OperationalError, ProgrammingError):
            self.db.rollback()
            return None
