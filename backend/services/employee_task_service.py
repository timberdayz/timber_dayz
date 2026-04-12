from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.employee_task_repository import EmployeeTaskRepository
from backend.services.employee_task_policy import can_user_perform_task_action


STATUS_PENDING = "pending"
STATUS_IN_PROGRESS = "in_progress"
STATUS_PENDING_CONFIRMATION = "pending_confirmation"
STATUS_COMPLETED = "completed"
STATUS_REJECTED = "rejected"
STATUS_CLOSED = "closed"


class EmployeeTaskService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repository = EmployeeTaskRepository(db)

    async def create_task(
        self,
        *,
        task_id: str,
        task_type: str,
        task_category: str,
        title: str,
        owner_user_id: int | None,
        created_by: int | None,
        source_type: str,
        source_module: str,
        description: str | None = None,
        source_record_type: str | None = None,
        source_record_id: str | None = None,
        priority: str = "medium",
        cc_user_ids: list[int] | None = None,
        collaborator_user_ids: list[int] | None = None,
        completion_schema: dict[str, Any] | None = None,
        due_at: datetime | None = None,
    ) -> dict[str, Any]:
        if not owner_user_id:
            raise ValueError("owner_user_id is required")

        cc_user_ids = cc_user_ids or []
        collaborator_user_ids = collaborator_user_ids or []

        task = await self.repository.create_task(
            task_id=task_id,
            task_type=task_type,
            task_category=task_category,
            title=title,
            description=description,
            status=STATUS_PENDING,
            priority=priority,
            owner_user_id=owner_user_id,
            created_by=created_by,
            source_type=source_type,
            source_module=source_module,
            source_record_type=source_record_type,
            source_record_id=source_record_id,
            completion_schema=completion_schema,
            due_at=due_at,
        )
        await self.repository.replace_participants(
            task_pk=task.id,
            cc_user_ids=cc_user_ids,
            collaborator_user_ids=collaborator_user_ids,
        )
        await self.repository.create_log(
            task_pk=task.id,
            actor_user_id=created_by,
            action="created",
            message="Task created",
            details_json={"status": STATUS_PENDING},
        )
        await self.db.commit()
        return await self.get_task_detail(task_id)

    async def list_tasks_for_user(self, *, user_id: int, scope: str) -> list[dict[str, Any]]:
        rows = await self.repository.list_tasks_for_user(user_id=user_id, scope=scope)
        return [await self._task_to_dict(row) for row in rows]

    async def get_task_detail(self, task_id: str, *, actor_user_id: int | None = None) -> dict[str, Any]:
        task = await self.repository.get_task_by_task_id(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        if actor_user_id is not None:
            await self._assert_task_visible(task, actor_user_id)
        return await self._task_to_dict(task, include_timeline=True)

    async def start_task(self, task_id: str, *, actor_user_id: int) -> dict[str, Any]:
        task = await self._get_owned_task(task_id, actor_user_id)
        await self.repository.update_task(
            task,
            status=STATUS_IN_PROGRESS,
            started_at=task.started_at or datetime.now(timezone.utc),
        )
        await self.repository.create_log(
            task_pk=task.id,
            actor_user_id=actor_user_id,
            action="started",
            message="Task started",
            details_json={"status": STATUS_IN_PROGRESS},
        )
        await self.db.commit()
        return await self.get_task_detail(task_id, actor_user_id=actor_user_id)

    async def submit_task_result(
        self,
        task_id: str,
        *,
        actor_user_id: int,
        completion_payload: dict[str, Any],
        result_comment: str | None = None,
        requires_confirmation: bool = False,
    ) -> dict[str, Any]:
        task = await self._get_owned_task(task_id, actor_user_id)
        next_status = STATUS_PENDING_CONFIRMATION if requires_confirmation else STATUS_COMPLETED
        now = datetime.now(timezone.utc)
        await self.repository.update_task(
            task,
            status=next_status,
            completion_payload=completion_payload,
            result_comment=result_comment,
            completed_at=now if not requires_confirmation else None,
            result_status="submitted",
        )
        await self.repository.create_log(
            task_pk=task.id,
            actor_user_id=actor_user_id,
            action="submitted",
            message="Task result submitted",
            details_json={"status": next_status},
        )
        await self.db.commit()
        return await self.get_task_detail(task_id, actor_user_id=actor_user_id)

    async def append_task_comment(
        self,
        task_id: str,
        *,
        actor_user_id: int,
        comment: str,
    ) -> dict[str, Any]:
        task = await self._get_visible_task(task_id, actor_user_id)
        await self._assert_can_supplement(task, actor_user_id, "append_comment")
        await self.repository.create_log(
            task_pk=task.id,
            actor_user_id=actor_user_id,
            action="append_comment",
            message=comment,
            details_json={"comment": comment},
        )
        await self.db.commit()
        return await self.get_task_detail(task_id, actor_user_id=actor_user_id)

    async def append_task_structured_data(
        self,
        task_id: str,
        *,
        actor_user_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        task = await self._get_visible_task(task_id, actor_user_id)
        await self._assert_can_supplement(task, actor_user_id, "append_structured_data")
        await self.repository.create_log(
            task_pk=task.id,
            actor_user_id=actor_user_id,
            action="append_structured_data",
            message="Structured supplement added",
            details_json=payload,
        )
        await self.db.commit()
        return await self.get_task_detail(task_id, actor_user_id=actor_user_id)

    async def close_task_as_initiator(
        self,
        task_id: str,
        *,
        actor_user_id: int,
        reason: str,
    ) -> dict[str, Any]:
        task = await self._get_visible_task(task_id, actor_user_id)
        if task.created_by != actor_user_id:
            raise ValueError("Only the initiator may close this task")
        if not can_user_perform_task_action(task.task_category, task.status, "initiator", "close_unstarted_task"):
            raise ValueError("Initiator may only directly close unstarted tasks")
        await self.repository.update_task(
            task,
            status=STATUS_CLOSED,
            closed_at=datetime.now(timezone.utc),
        )
        await self.repository.create_log(
            task_pk=task.id,
            actor_user_id=actor_user_id,
            action="close_unstarted_task",
            message=reason,
            details_json={"reason": reason},
        )
        await self.db.commit()
        return await self.get_task_detail(task_id, actor_user_id=actor_user_id)

    async def request_task_cancellation(
        self,
        task_id: str,
        *,
        actor_user_id: int,
        reason: str,
    ) -> dict[str, Any]:
        task = await self._get_visible_task(task_id, actor_user_id)
        if task.created_by != actor_user_id:
            raise ValueError("Only the initiator may request task cancellation")
        if not can_user_perform_task_action(task.task_category, task.status, "initiator", "request_cancel"):
            raise ValueError("Initiator may only request cancellation after the task has started")
        await self.repository.create_log(
            task_pk=task.id,
            actor_user_id=actor_user_id,
            action="request_cancel",
            message=reason,
            details_json={"reason": reason},
        )
        await self.db.commit()
        return await self.get_task_detail(task_id, actor_user_id=actor_user_id)

    async def _get_owned_task(self, task_id: str, actor_user_id: int):
        task = await self.repository.get_task_by_task_id(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        if task.owner_user_id != actor_user_id:
            raise ValueError("Only the task owner may perform this action")
        return task

    async def _get_visible_task(self, task_id: str, actor_user_id: int):
        task = await self.repository.get_task_by_task_id(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        await self._assert_task_visible(task, actor_user_id)
        return task

    async def _assert_can_supplement(self, task, actor_user_id: int, action: str) -> None:
        if task.owner_user_id == actor_user_id:
            return
        participants = await self.repository.list_participants(task.id)
        collaborator = next((row for row in participants if row.user_id == actor_user_id and row.participant_role == "collaborator"), None)
        if collaborator and can_user_perform_task_action(task.task_category, task.status, "collaborator", action):
            return
        raise ValueError("Only task collaborators or the owner may supplement this task")

    async def _assert_task_visible(self, task, actor_user_id: int) -> None:
        if task.owner_user_id == actor_user_id:
            return
        if task.created_by == actor_user_id:
            return
        participants = await self.repository.list_participants(task.id)
        if any(row.user_id == actor_user_id for row in participants):
            return
        raise ValueError("Access denied for this task")

    async def _task_to_dict(self, task, *, include_timeline: bool = False) -> dict[str, Any]:
        participants = await self.repository.list_participants(task.id)
        cc_user_ids = [row.user_id for row in participants if row.participant_role == "cc"]
        collaborator_user_ids = [
            row.user_id for row in participants if row.participant_role == "collaborator"
        ]

        payload = {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "task_category": task.task_category,
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "priority": task.priority,
            "owner_user_id": task.owner_user_id,
            "created_by": task.created_by,
            "source_type": task.source_type,
            "source_module": task.source_module,
            "source_record_type": task.source_record_type,
            "source_record_id": task.source_record_id,
            "cc_user_ids": cc_user_ids,
            "collaborator_user_ids": collaborator_user_ids,
            "completion_schema": task.completion_schema or {},
            "completion_payload": task.completion_payload or {},
            "result_status": task.result_status,
            "result_comment": task.result_comment,
            "due_at": self._iso(task.due_at),
            "started_at": self._iso(task.started_at),
            "completed_at": self._iso(task.completed_at),
            "closed_at": self._iso(task.closed_at),
            "created_at": self._iso(task.created_at),
            "updated_at": self._iso(task.updated_at),
        }

        if include_timeline:
            logs = await self.repository.list_logs(task.id)
            payload["timeline"] = [
                {
                    "id": row.id,
                    "actor_user_id": row.actor_user_id,
                    "action": row.action,
                    "message": row.message,
                    "details_json": row.details_json or {},
                    "created_at": self._iso(row.created_at),
                }
                for row in logs
            ]

        return payload

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
