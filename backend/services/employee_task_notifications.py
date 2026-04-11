from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.routers.notifications import create_notification
from backend.schemas.notification import NotificationType


async def notify_task_assigned(
    *,
    db: AsyncSession,
    recipient_id: int,
    task_id: str,
    task_type: str,
    source_module: str,
    source_record_type: str | None,
    source_record_id: str | None,
    title: str,
    content: str,
):
    return await create_notification(
        db=db,
        recipient_id=recipient_id,
        notification_type=NotificationType.TASK_ASSIGNED,
        title=title,
        content=content,
        extra_data={
            "task_id": task_id,
            "task_type": task_type,
            "source_module": source_module,
            "source_record_type": source_record_type,
            "source_record_id": source_record_id,
            "target_route": f"/my-tasks/{task_id}",
        },
        priority="high",
    )
