from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import TaskCenterLink, TaskCenterLog, TaskCenterTask


class TaskCenterRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_task(self, **fields: Any) -> TaskCenterTask:
        task = TaskCenterTask(**fields)
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def get_task_by_task_id(self, task_id: str) -> TaskCenterTask | None:
        result = await self.db.execute(
            select(TaskCenterTask).where(TaskCenterTask.task_id == task_id)
        )
        return result.scalar_one_or_none()

    async def update_task(self, task: TaskCenterTask, **updates: Any) -> TaskCenterTask:
        for key, value in updates.items():
            if hasattr(task, key):
                setattr(task, key, value)
        task.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def create_log(self, **fields: Any) -> TaskCenterLog:
        log = TaskCenterLog(**fields)
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def create_link(self, **fields: Any) -> TaskCenterLink:
        link = TaskCenterLink(**fields)
        self.db.add(link)
        await self.db.commit()
        await self.db.refresh(link)
        return link

    async def delete_task(self, task: TaskCenterTask) -> None:
        await self.db.delete(task)
        await self.db.commit()

    async def list_tasks(
        self,
        *,
        task_family: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TaskCenterTask]:
        stmt: Select[tuple[TaskCenterTask]] = select(TaskCenterTask)
        if task_family:
            stmt = stmt.where(TaskCenterTask.task_family == task_family)
        if status:
            stmt = stmt.where(TaskCenterTask.status == status)
        stmt = stmt.order_by(TaskCenterTask.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_logs(self, task_pk: int, *, limit: int = 200) -> list[TaskCenterLog]:
        result = await self.db.execute(
            select(TaskCenterLog)
            .where(TaskCenterLog.task_pk == task_pk)
            .order_by(TaskCenterLog.created_at.asc(), TaskCenterLog.id.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_subject(
        self,
        *,
        subject_type: str,
        subject_id: str | None = None,
        subject_key: str | None = None,
        limit: int = 100,
    ) -> list[TaskCenterTask]:
        stmt = (
            select(TaskCenterTask)
            .join(TaskCenterLink, TaskCenterLink.task_pk == TaskCenterTask.id)
            .where(TaskCenterLink.subject_type == subject_type)
        )
        if subject_id is not None:
            stmt = stmt.where(TaskCenterLink.subject_id == subject_id)
        if subject_key is not None:
            stmt = stmt.where(TaskCenterLink.subject_key == subject_key)
        stmt = stmt.order_by(TaskCenterTask.created_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
