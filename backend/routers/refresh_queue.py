from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import get_current_user
from backend.models.database import get_async_db
from backend.services.data_pipeline.refresh_queue_service import RefreshQueueService
from backend.utils.api_response import error_response, success_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/refresh-queue", tags=["Refresh Queue"])


@router.get("/tasks")
async def list_refresh_queue_tasks(
    status: str | None = Query(None, description="任务状态"),
    limit: int = Query(100, ge=1, le=500, description="返回数量限制"),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    try:
        service = RefreshQueueService(db)
        rows = await service.list_tasks(status=status, limit=limit)
        data = [
            {
                "id": row.id,
                "job_id": row.job_id,
                "trigger_type": row.trigger_type,
                "pipeline_name": row.pipeline_name,
                "dedupe_key": row.dedupe_key,
                "targets_json": row.targets_json or [],
                "context_json": row.context_json or {},
                "status": row.status,
                "attempt_count": row.attempt_count,
                "last_error": row.last_error,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            }
            for row in rows
        ]
        return success_response(data=data, message=f"获取到{len(data)}条refresh queue任务")
    except Exception as exc:
        logger.error("[RefreshQueueAPI] 获取任务失败: %s", exc, exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取 refresh queue 任务失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            status_code=500,
        )


@router.post("/tasks/{task_id}/retry")
async def retry_refresh_queue_task(
    task_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    try:
        service = RefreshQueueService(db)
        row = await service.retry_failed_task(task_id)
        return success_response(
            data={
                "id": row.id,
                "job_id": row.job_id,
                "status": row.status,
                "attempt_count": row.attempt_count,
                "last_error": row.last_error,
            },
            message="refresh queue 任务已重试",
        )
    except ValueError as exc:
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="重试 refresh queue 任务失败",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            detail=str(exc),
            status_code=400,
        )
    except Exception as exc:
        logger.error("[RefreshQueueAPI] 重试任务失败: %s", exc, exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="重试 refresh queue 任务失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            status_code=500,
        )
