from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import RefreshQueueTask


class RefreshQueueService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def build_dedupe_key(pipeline_name: str, targets: list[str]) -> str:
        normalized_targets = sorted(str(target).strip() for target in targets if str(target).strip())
        payload = json.dumps(
            {
                "pipeline_name": str(pipeline_name or "").strip(),
                "targets": normalized_targets,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _merge_context(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = dict(existing or {})
        for key, value in (incoming or {}).items():
            if isinstance(value, list) and isinstance(merged.get(key), list):
                merged[key] = list(dict.fromkeys([*merged[key], *value]))
            elif isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
        return merged

    async def enqueue_refresh(
        self,
        *,
        trigger_type: str,
        pipeline_name: str,
        targets: list[str],
        context: dict[str, Any] | None = None,
    ) -> RefreshQueueTask:
        dedupe_key = self.build_dedupe_key(pipeline_name, targets)
        existing = await self._get_pending_by_dedupe_key(dedupe_key)
        if existing:
            existing.context_json = self._merge_context(existing.context_json or {}, context or {})
            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        task = RefreshQueueTask(
            job_id=f"refresh-{uuid.uuid4().hex}",
            trigger_type=trigger_type,
            pipeline_name=pipeline_name,
            dedupe_key=dedupe_key,
            targets_json=sorted(str(target).strip() for target in targets if str(target).strip()),
            context_json=context or {},
            status="pending",
            attempt_count=0,
        )
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def claim_next_refresh_task(self) -> RefreshQueueTask | None:
        running_result = await self.db.execute(
            select(RefreshQueueTask.id)
            .where(RefreshQueueTask.status == "running")
            .limit(1)
        )
        if running_result.scalar_one_or_none() is not None:
            return None

        stmt: Select[tuple[RefreshQueueTask]] = (
            select(RefreshQueueTask)
            .where(RefreshQueueTask.status == "pending")
            .order_by(RefreshQueueTask.created_at.asc(), RefreshQueueTask.id.asc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        task = result.scalar_one_or_none()
        if task is None:
            return None

        task.status = "running"
        task.attempt_count = (task.attempt_count or 0) + 1
        task.started_at = datetime.now(timezone.utc)
        task.last_error = None
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def mark_completed(self, task_id: int) -> RefreshQueueTask:
        task = await self.db.get(RefreshQueueTask, task_id)
        if task is None:
            raise ValueError(f"refresh queue task {task_id} not found")
        task.status = "completed"
        task.finished_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def mark_failed(self, task_id: int, error_message: str) -> RefreshQueueTask:
        task = await self.db.get(RefreshQueueTask, task_id)
        if task is None:
            raise ValueError(f"refresh queue task {task_id} not found")
        task.status = "failed"
        task.last_error = error_message
        task.finished_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def list_tasks(self, *, status: str | None = None, limit: int = 100) -> list[RefreshQueueTask]:
        stmt: Select[tuple[RefreshQueueTask]] = select(RefreshQueueTask).order_by(
            RefreshQueueTask.created_at.desc(),
            RefreshQueueTask.id.desc(),
        )
        if status:
            stmt = stmt.where(RefreshQueueTask.status == status)
        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def _get_pending_by_dedupe_key(self, dedupe_key: str) -> RefreshQueueTask | None:
        result = await self.db.execute(
            select(RefreshQueueTask)
            .where(
                RefreshQueueTask.dedupe_key == dedupe_key,
                RefreshQueueTask.status == "pending",
            )
            .order_by(RefreshQueueTask.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()
