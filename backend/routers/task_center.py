from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_async_db
from backend.services.task_center_service import TaskCenterService
from backend.utils.api_response import success_response

router = APIRouter()


@router.get("/task-center/tasks")
async def list_task_center_tasks(
    family: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
):
    service = TaskCenterService(db)
    offset = (page - 1) * page_size
    items = await service.list_tasks(
        task_family=family,
        status=status,
        limit=page_size,
        offset=offset,
    )
    return success_response(
        data={
            "items": items,
            "total": len(items),
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/task-center/tasks/by-subject")
async def list_task_center_tasks_by_subject(
    subject_type: str = Query(...),
    subject_id: str | None = Query(None),
    subject_key: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_async_db),
):
    service = TaskCenterService(db)
    items = await service.list_by_subject(
        subject_type=subject_type,
        subject_id=subject_id,
        subject_key=subject_key,
        limit=limit,
    )
    return success_response(data={"items": items, "total": len(items)})


@router.get("/task-center/tasks/{task_id}")
async def get_task_center_task(
    task_id: str,
    db: AsyncSession = Depends(get_async_db),
):
    service = TaskCenterService(db)
    task = await service.get_task(task_id)
    return success_response(data=task)


@router.get("/task-center/tasks/{task_id}/logs")
async def get_task_center_logs(
    task_id: str,
    limit: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_async_db),
):
    service = TaskCenterService(db)
    logs = await service.list_logs(task_id, limit=limit)
    return success_response(data={"items": logs})
