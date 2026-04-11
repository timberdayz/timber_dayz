from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import EmployeeTask, EmployeeTaskLog, EmployeeTaskParticipant


class EmployeeTaskRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_task(self, **fields: Any) -> EmployeeTask:
        task = EmployeeTask(**fields)
        self.db.add(task)
        await self.db.flush()
        return task

    async def get_task_by_task_id(self, task_id: str) -> EmployeeTask | None:
        result = await self.db.execute(
            select(EmployeeTask).where(EmployeeTask.task_id == task_id)
        )
        return result.scalar_one_or_none()

    async def update_task(self, task: EmployeeTask, **updates: Any) -> EmployeeTask:
        for key, value in updates.items():
            if hasattr(task, key):
                setattr(task, key, value)
        task.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return task

    async def create_log(self, **fields: Any) -> EmployeeTaskLog:
        log = EmployeeTaskLog(**fields)
        self.db.add(log)
        await self.db.flush()
        return log

    async def replace_participants(
        self,
        *,
        task_pk: int,
        cc_user_ids: list[int],
        collaborator_user_ids: list[int],
    ) -> None:
        result = await self.db.execute(
            select(EmployeeTaskParticipant).where(EmployeeTaskParticipant.task_pk == task_pk)
        )
        for row in result.scalars().all():
            await self.db.delete(row)

        for user_id in cc_user_ids:
            self.db.add(
                EmployeeTaskParticipant(
                    task_pk=task_pk,
                    user_id=user_id,
                    participant_role="cc",
                )
            )
        for user_id in collaborator_user_ids:
            self.db.add(
                EmployeeTaskParticipant(
                    task_pk=task_pk,
                    user_id=user_id,
                    participant_role="collaborator",
                )
            )
        await self.db.flush()

    async def list_tasks_for_user(
        self,
        *,
        user_id: int,
        scope: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EmployeeTask]:
        stmt: Select[tuple[EmployeeTask]] = select(EmployeeTask)

        if scope == "owner":
            stmt = stmt.where(EmployeeTask.owner_user_id == user_id)
        elif scope == "initiated":
            stmt = stmt.where(EmployeeTask.created_by == user_id)
        elif scope == "cc":
            stmt = (
                stmt.join(EmployeeTaskParticipant, EmployeeTaskParticipant.task_pk == EmployeeTask.id)
                .where(
                    EmployeeTaskParticipant.user_id == user_id,
                    EmployeeTaskParticipant.participant_role == "cc",
                )
            )
        elif scope == "collaborator":
            stmt = (
                stmt.join(EmployeeTaskParticipant, EmployeeTaskParticipant.task_pk == EmployeeTask.id)
                .where(
                    EmployeeTaskParticipant.user_id == user_id,
                    EmployeeTaskParticipant.participant_role == "collaborator",
                )
            )
        else:
            raise ValueError(f"Unsupported scope: {scope}")

        stmt = stmt.order_by(EmployeeTask.created_at.desc(), EmployeeTask.id.desc()).offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_logs(self, task_pk: int) -> list[EmployeeTaskLog]:
        result = await self.db.execute(
            select(EmployeeTaskLog)
            .where(EmployeeTaskLog.task_pk == task_pk)
            .order_by(EmployeeTaskLog.created_at.asc(), EmployeeTaskLog.id.asc())
        )
        return list(result.scalars().all())

    async def list_participants(self, task_pk: int) -> list[EmployeeTaskParticipant]:
        result = await self.db.execute(
            select(EmployeeTaskParticipant).where(EmployeeTaskParticipant.task_pk == task_pk)
        )
        return list(result.scalars().all())
