from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.task_center_repository import TaskCenterRepository


class TaskCenterService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repository = TaskCenterRepository(db)

    async def create_task(self, **fields: Any) -> dict[str, Any]:
        payload = {
            "status": "pending",
            "details_json": {},
            **fields,
        }
        task = await self.repository.create_task(**payload)
        return self._task_to_dict(task)

    async def get_task(self, task_id: str) -> dict[str, Any] | None:
        task = await self.repository.get_task_by_task_id(task_id)
        if task is None:
            return None
        return self._task_to_dict(task)

    async def update_task(self, task_id: str, **updates: Any) -> dict[str, Any]:
        task = await self.repository.get_task_by_task_id(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        if "details_json" in updates and isinstance(updates["details_json"], dict):
            current = task.details_json or {}
            updates["details_json"] = {**current, **updates["details_json"]}

        task = await self.repository.update_task(task, **updates)
        return self._task_to_dict(task)

    async def set_runner(
        self,
        task_id: str,
        *,
        runner_kind: str,
        external_runner_id: str,
    ) -> dict[str, Any]:
        return await self.update_task(
            task_id,
            runner_kind=runner_kind,
            external_runner_id=external_runner_id,
        )

    async def append_log(
        self,
        task_id: str,
        *,
        level: str,
        event_type: str,
        message: str,
        details_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        task = await self.repository.get_task_by_task_id(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        log = await self.repository.create_log(
            task_pk=task.id,
            level=level,
            event_type=event_type,
            message=message,
            details_json=details_json,
        )
        return self._log_to_dict(log)

    async def add_link(
        self,
        task_id: str,
        *,
        subject_type: str,
        subject_id: str | None = None,
        subject_key: str | None = None,
        details_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        task = await self.repository.get_task_by_task_id(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        link = await self.repository.create_link(
            task_pk=task.id,
            subject_type=subject_type,
            subject_id=subject_id,
            subject_key=subject_key,
            details_json=details_json,
        )
        return self._link_to_dict(link)

    async def list_tasks(
        self,
        *,
        task_family: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        rows = await self.repository.list_tasks(
            task_family=task_family,
            status=status,
            limit=limit,
            offset=offset,
        )
        return [self._task_to_dict(row) for row in rows]

    async def list_logs(self, task_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        task = await self.repository.get_task_by_task_id(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        rows = await self.repository.list_logs(task.id, limit=limit)
        return [self._log_to_dict(row) for row in rows]

    async def list_by_subject(
        self,
        *,
        subject_type: str,
        subject_id: str | None = None,
        subject_key: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        rows = await self.repository.list_by_subject(
            subject_type=subject_type,
            subject_id=subject_id,
            subject_key=subject_key,
            limit=limit,
        )
        return [self._task_to_dict(row) for row in rows]

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()

    def _task_to_dict(self, task) -> dict[str, Any]:
        return {
            "task_id": task.task_id,
            "task_family": task.task_family,
            "task_type": task.task_type,
            "status": task.status,
            "trigger_source": task.trigger_source,
            "priority": task.priority,
            "runner_kind": task.runner_kind,
            "external_runner_id": task.external_runner_id,
            "parent_task_id": task.parent_task_id,
            "attempt_count": task.attempt_count,
            "next_retry_at": self._iso(task.next_retry_at),
            "claimed_by": task.claimed_by,
            "lease_expires_at": self._iso(task.lease_expires_at),
            "heartbeat_at": self._iso(task.heartbeat_at),
            "platform_code": task.platform_code,
            "account_id": task.account_id,
            "source_file_id": task.source_file_id,
            "source_table_name": task.source_table_name,
            "current_step": task.current_step,
            "current_item": task.current_item,
            "total_items": task.total_items,
            "processed_items": task.processed_items,
            "success_items": task.success_items,
            "failed_items": task.failed_items,
            "skipped_items": task.skipped_items,
            "total_rows": task.total_rows,
            "processed_rows": task.processed_rows,
            "valid_rows": task.valid_rows,
            "error_rows": task.error_rows,
            "quarantined_rows": task.quarantined_rows,
            "progress_percent": task.progress_percent,
            "error_summary": task.error_summary,
            "details_json": task.details_json or {},
            "created_at": self._iso(task.created_at),
            "started_at": self._iso(task.started_at),
            "updated_at": self._iso(task.updated_at),
            "finished_at": self._iso(task.finished_at),
        }

    def _log_to_dict(self, log) -> dict[str, Any]:
        return {
            "id": log.id,
            "task_pk": log.task_pk,
            "level": log.level,
            "event_type": log.event_type,
            "message": log.message,
            "details_json": log.details_json or {},
            "created_at": self._iso(log.created_at),
        }

    def _link_to_dict(self, link) -> dict[str, Any]:
        return {
            "id": link.id,
            "task_pk": link.task_pk,
            "subject_type": link.subject_type,
            "subject_id": link.subject_id,
            "subject_key": link.subject_key,
            "details_json": link.details_json or {},
            "created_at": self._iso(link.created_at),
        }
