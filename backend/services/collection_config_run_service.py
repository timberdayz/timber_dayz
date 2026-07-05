from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import CollectionConfig, CollectionConfigRun, CollectionTask


TERMINAL_TASK_STATUSES = {
    "completed",
    "partial_success",
    "failed",
    "cancelled",
    "interrupted",
}

ACTIVE_RUN_STATUSES = {"queued", "running"}
TERMINAL_RUN_STATUSES = {"completed", "partial_success", "failed", "cancelled"}
RECOVERABLE_TASK_STATUSES = {
    "pending",
    "queued",
    "running",
    "paused",
    "verification_required",
    "verification_submitted",
    "manual_intervention_required",
}


class CollectionConfigRunService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def enqueue_config_run(
        self,
        config: CollectionConfig,
        *,
        trigger_type: str,
        priority: int = 5,
    ) -> Tuple[CollectionConfigRun, bool]:
        existing = (
            await self.db.execute(
                select(CollectionConfigRun).where(
                    CollectionConfigRun.config_id == config.id,
                    CollectionConfigRun.status.in_(ACTIVE_RUN_STATUSES),
                )
            )
        ).scalars().first()
        if existing is not None:
            return existing, False

        run = CollectionConfigRun(
            run_id=str(uuid.uuid4()),
            config_id=config.id,
            platform=config.platform,
            main_account_id=config.main_account_id,
            trigger_type=trigger_type,
            status="queued",
            priority=priority,
            scheduled_for=datetime.now(timezone.utc)
            if str(trigger_type).strip().lower() == "scheduled"
            else None,
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run, True

    async def get_running_run(self) -> CollectionConfigRun | None:
        return (
            await self.db.execute(
                select(CollectionConfigRun).where(CollectionConfigRun.status == "running")
            )
        ).scalars().first()

    async def claim_next_queued_run(self) -> CollectionConfigRun | None:
        running = await self.get_running_run()
        if running is not None:
            return None

        queued = (
            await self.db.execute(
                select(CollectionConfigRun)
                .where(CollectionConfigRun.status == "queued")
                .order_by(CollectionConfigRun.created_at, CollectionConfigRun.id)
            )
        ).scalars().first()
        if queued is None:
            return None

        queued.status = "running"
        queued.started_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(queued)
        return queued

    async def cancel_run_by_run_id(self, run_id: str) -> CollectionConfigRun:
        run = (
            await self.db.execute(
                select(CollectionConfigRun).where(CollectionConfigRun.run_id == run_id)
            )
        ).scalars().first()
        if run is None:
            raise ValueError(f"CollectionConfigRun not found: {run_id}")
        if run.status in TERMINAL_RUN_STATUSES:
            raise ValueError("terminal config runs cannot be cancelled")
        if run.status not in ACTIVE_RUN_STATUSES:
            raise ValueError(f"config run status cannot be cancelled: {run.status}")

        now = datetime.now(timezone.utc)
        run.status = "cancelled"
        run.completed_at = now
        run.error_message = "user cancelled config run"

        tasks = (
            await self.db.execute(
                select(CollectionTask).where(
                    CollectionTask.config_run_id == run.id,
                    CollectionTask.status.in_(RECOVERABLE_TASK_STATUSES),
                )
            )
        ).scalars().all()
        for task in tasks:
            task.status = "cancelled"
            task.error_message = "user cancelled config run"
            task.completed_at = now

        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def mark_run_failed(
        self,
        run_id: int,
        *,
        error_message: str,
    ) -> CollectionConfigRun:
        run = await self._get_run(run_id)
        if run.status == "cancelled":
            return run
        run.status = "failed"
        run.error_message = error_message
        run.completed_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def mark_running_runs_failed(
        self,
        *,
        error_message: str,
    ) -> list[CollectionConfigRun]:
        runs = (
            await self.db.execute(
                select(CollectionConfigRun).where(CollectionConfigRun.status == "running")
            )
        ).scalars().all()

        if not runs:
            return []

        now = datetime.now(timezone.utc)
        run_ids = [run.id for run in runs]
        tasks = (
            await self.db.execute(
                select(CollectionTask).where(
                    CollectionTask.config_run_id.in_(run_ids),
                    CollectionTask.status.in_(RECOVERABLE_TASK_STATUSES),
                )
            )
        ).scalars().all()

        for run in runs:
            run.status = "failed"
            run.error_message = error_message
            run.completed_at = now

        for task in tasks:
            task.status = "failed"
            task.error_message = error_message
            task.completed_at = now

        await self.db.commit()
        for run in runs:
            await self.db.refresh(run)
        return list(runs)

    async def finalize_run_from_tasks(self, run_id: int) -> CollectionConfigRun:
        run = await self._get_run(run_id)
        if run.status == "cancelled":
            return run
        tasks = (
            await self.db.execute(
                select(CollectionTask).where(CollectionTask.config_run_id == run_id)
            )
        ).scalars().all()

        statuses = {task.status for task in tasks}
        if not statuses:
            run.status = "failed"
            run.error_message = "config run finished without collection tasks"
        elif any(status not in TERMINAL_TASK_STATUSES for status in statuses):
            return run
        elif statuses <= {"completed"}:
            run.status = "completed"
        elif statuses <= {"cancelled"}:
            run.status = "cancelled"
        elif statuses <= {"failed", "cancelled", "interrupted"}:
            run.status = "failed"
        else:
            run.status = "partial_success"

        run.completed_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def _get_run(self, run_id: int) -> CollectionConfigRun:
        run = (
            await self.db.execute(
                select(CollectionConfigRun).where(CollectionConfigRun.id == run_id)
            )
        ).scalars().first()
        if run is None:
            raise ValueError(f"CollectionConfigRun not found: {run_id}")
        return run
