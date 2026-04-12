from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import ApprovalActionLog, ApprovalInstance, ApprovalStep, ApprovalTemplate


class ApprovalCenterRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_template_by_code(self, template_code: str) -> ApprovalTemplate | None:
        result = await self.db.execute(
            select(ApprovalTemplate).where(ApprovalTemplate.template_code == template_code)
        )
        return result.scalar_one_or_none()

    async def create_instance(self, **fields: Any) -> ApprovalInstance:
        instance = ApprovalInstance(**fields)
        self.db.add(instance)
        await self.db.flush()
        return instance

    async def get_instance_by_approval_id(self, approval_id: str) -> ApprovalInstance | None:
        result = await self.db.execute(
            select(ApprovalInstance).where(ApprovalInstance.approval_id == approval_id)
        )
        return result.scalar_one_or_none()

    async def update_instance(self, instance: ApprovalInstance, **updates: Any) -> ApprovalInstance:
        for key, value in updates.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
        instance.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return instance

    async def create_step(self, **fields: Any) -> ApprovalStep:
        step = ApprovalStep(**fields)
        self.db.add(step)
        await self.db.flush()
        return step

    async def get_pending_step(self, approval_pk: int) -> ApprovalStep | None:
        result = await self.db.execute(
            select(ApprovalStep)
            .where(ApprovalStep.approval_pk == approval_pk, ApprovalStep.status == "pending")
            .order_by(ApprovalStep.step_order.asc(), ApprovalStep.id.asc())
        )
        return result.scalars().first()

    async def list_steps(self, approval_pk: int) -> list[ApprovalStep]:
        result = await self.db.execute(
            select(ApprovalStep)
            .where(ApprovalStep.approval_pk == approval_pk)
            .order_by(ApprovalStep.step_order.asc(), ApprovalStep.id.asc())
        )
        return list(result.scalars().all())

    async def update_step(self, step: ApprovalStep, **updates: Any) -> ApprovalStep:
        for key, value in updates.items():
            if hasattr(step, key):
                setattr(step, key, value)
        await self.db.flush()
        return step

    async def create_action_log(self, **fields: Any) -> ApprovalActionLog:
        log = ApprovalActionLog(**fields)
        self.db.add(log)
        await self.db.flush()
        return log

    async def list_action_logs(self, approval_pk: int) -> list[ApprovalActionLog]:
        result = await self.db.execute(
            select(ApprovalActionLog)
            .where(ApprovalActionLog.approval_pk == approval_pk)
            .order_by(ApprovalActionLog.created_at.asc(), ApprovalActionLog.id.asc())
        )
        return list(result.scalars().all())
