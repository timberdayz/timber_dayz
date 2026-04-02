"""
数据采集模块 - 任务管理 API

拆分自 collection.py，包含任务 CRUD、重试、恢复、日志、截图、历史统计端点，
以及后台执行、步骤回调等辅助函数。
"""

import os
import uuid
import asyncio
import inspect
from datetime import datetime, date, timedelta, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Path
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import desc, select

from backend.models.database import get_async_db
from modules.core.db import CollectionTask, CollectionTaskLog
from modules.core.logger import get_logger
from backend.schemas.collection import (
    TaskCreateRequest,
    ResumeTaskRequest,
    TaskResponse,
    CollectionVerificationItem,
    TaskLogResponse,
    TaskHistoryResponse,
    TaskStatsResponse,
    DailyStats,
)
from backend.schemas.common import SuccessResponse
from backend.services.collection_contracts import (
    build_date_range_from_time_selection,
    count_collection_targets,
    derive_granularity_from_time_selection,
    normalize_collection_date_range,
    normalize_domain_subtypes,
    normalize_time_selection,
)
from backend.services.task_center_service import TaskCenterService
from backend.services.verification_protocol import (
    extract_resume_submission,
    verification_input_mode,
)
from backend.services.websocket_manager import connection_manager

logger = get_logger(__name__)

router = APIRouter(tags=["数据采集-任务"])

TERMINAL_TASK_STATUSES = frozenset({"completed", "failed", "cancelled", "partial_success"})

CAPTCHA_REDIS_KEY_PREFIX = "collection:captcha:"

VERIFICATION_WAIT_TIMEOUT = int(os.getenv("VERIFICATION_TIMEOUT", "300"))
VERIFICATION_POLL_INTERVAL = 1.5


def _collection_task_details_payload(task: CollectionTask) -> dict:
    return {
        "collection": {
            "raw_status": getattr(task, "status", None),
            "config_id": getattr(task, "config_id", None),
            "trigger_type": getattr(task, "trigger_type", None),
            "data_domains": getattr(task, "data_domains", None),
            "sub_domains": getattr(task, "sub_domains", None),
            "granularity": getattr(task, "granularity", None),
            "date_range": getattr(task, "date_range", None),
            "total_domains": getattr(task, "total_domains", 0),
            "completed_domains": getattr(task, "completed_domains", None),
            "failed_domains": getattr(task, "failed_domains", None),
            "current_domain": getattr(task, "current_domain", None),
            "debug_mode": getattr(task, "debug_mode", False),
            "verification_type": getattr(task, "verification_type", None),
            "verification_screenshot": getattr(task, "verification_screenshot", None),
        }
    }


def _collection_status_to_task_center(status: Optional[str]) -> Optional[str]:
    if status is None:
        return None
    return {
        "verification_required": "paused",
        "verification_submitted": "running",
    }.get(status, status)


async def _mirror_collection_task(
    db: AsyncSession,
    task: CollectionTask,
) -> dict:
    from backend.services.task_center_service import TaskCenterService

    try:
        service = TaskCenterService(db)
        payload = {
            "task_family": "collection",
            "task_type": getattr(task, "trigger_type", None) or "manual",
            "status": _collection_status_to_task_center(getattr(task, "status", None)) or "pending",
            "trigger_source": getattr(task, "trigger_type", None),
            "platform_code": getattr(task, "platform", None),
            "account_id": getattr(task, "account", None),
            "current_step": getattr(task, "current_step", None),
            "progress_percent": float(getattr(task, "progress", 0) or 0),
            "success_items": len(getattr(task, "completed_domains", None) or []),
            "failed_items": len(getattr(task, "failed_domains", None) or []),
            "details_json": _collection_task_details_payload(task),
            "started_at": getattr(task, "started_at", None),
            "finished_at": getattr(task, "completed_at", None),
            "error_summary": getattr(task, "error_message", None),
        }

        existing = await service.get_task(task.task_id)
        if existing:
            return await service.update_task(task.task_id, **payload)
        return await service.create_task(task_id=task.task_id, **payload)
    except Exception as exc:
        logger.debug("Collection task mirror skipped for %s: %s", getattr(task, "task_id", "unknown"), exc)
        return {}


async def _mirror_collection_task_log(
    db: AsyncSession,
    task_id: str,
    *,
    level: str,
    event_type: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    from backend.services.task_center_service import TaskCenterService

    try:
        service = TaskCenterService(db)
        task = await service.get_task(task_id)
        if task is None:
            return
        await service.append_log(
            task_id,
            level=level,
            event_type=event_type,
            message=message,
            details_json=details,
        )
    except Exception as exc:
        logger.debug("Collection task log mirror skipped for %s: %s", task_id, exc)


# ============================================================
# 任务 API
# ============================================================

def _build_task_response_payload(task: CollectionTask) -> dict:
    normalized_date_range = normalize_collection_date_range(getattr(task, "date_range", None))
    time_selection = None
    if "time_selection" in normalized_date_range:
        time_selection = normalized_date_range.pop("time_selection")
    elif isinstance(getattr(task, "date_range", None), dict):
        time_selection = task.date_range.get("time_selection")
    if time_selection is None:
        time_selection = getattr(task, "time_selection", None)

    verification_type = getattr(task, "verification_type", None)
    verification_message = None
    if verification_type:
        verification_message = getattr(task, "current_step", None) or getattr(
            task, "error_message", None
        )

    return {
        "id": task.id,
        "task_id": task.task_id,
        "platform": task.platform,
        "account": task.account,
        "status": task.status,
        "progress": getattr(task, "progress", 0) or 0,
        "current_step": getattr(task, "current_step", None),
        "files_collected": getattr(task, "files_collected", 0) or 0,
        "trigger_type": task.trigger_type,
        "config_id": getattr(task, "config_id", None),
        "data_domains": getattr(task, "data_domains", None),
        "sub_domains": getattr(task, "sub_domains", None),
        "granularity": getattr(task, "granularity", None),
        "date_range": normalized_date_range,
        "time_selection": time_selection,
        "total_domains": getattr(task, "total_domains", 0) or 0,
        "completed_domains": getattr(task, "completed_domains", None),
        "failed_domains": getattr(task, "failed_domains", None),
        "current_domain": getattr(task, "current_domain", None),
        "debug_mode": getattr(task, "debug_mode", False) or False,
        "execution_mode": "headed" if getattr(task, "debug_mode", False) else "headless",
        "error_message": getattr(task, "error_message", None),
        "duration_seconds": getattr(task, "duration_seconds", None),
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "started_at": getattr(task, "started_at", None),
        "completed_at": getattr(task, "completed_at", None),
        "verification_type": verification_type,
        "verification_screenshot": getattr(task, "verification_screenshot", None),
        "verification_id": task.task_id if verification_type else None,
        "verification_message": verification_message,
        "verification_expires_at": None,
        "verification_attempt_count": 0,
        "verification_input_mode": verification_input_mode(verification_type)
        if verification_type
        else None,
    }


def _build_task_verification_item(task: CollectionTask) -> Optional[dict]:
    if getattr(task, "status", None) not in ("verification_required", "paused", "manual_intervention_required") or not getattr(
        task, "verification_type", None
    ):
        return None

    return {
        "task_id": task.task_id,
        "account_id": task.account,
        "verification_id": task.task_id,
        "platform": task.platform,
        "status": task.status,
        "verification_type": task.verification_type,
        "verification_message": getattr(task, "current_step", None)
        or getattr(task, "error_message", None),
        "verification_screenshot": getattr(task, "verification_screenshot", None),
        "verification_expires_at": None,
        "verification_attempt_count": 0,
        "verification_input_mode": verification_input_mode(
            getattr(task, "verification_type", None)
        ),
        "created_at": getattr(task, "created_at", None),
    }


@router.post("/tasks", response_model=TaskResponse)
async def create_task(
    request: TaskCreateRequest,
    fastapi_request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """
    创建采集任务(v4.7.0)

    v4.7.0 更新:
    - 支持子域数组(sub_domains)
    - 支持调试模式(debug_mode)
    - 支持任务粒度优化(一账号一任务,循环采集所有域)
    - 支持账号能力过滤(capabilities)
    """
    task_uuid = str(uuid.uuid4())

    from backend.services.task_service import TaskService
    from backend.services.component_runtime_resolver import (
        ComponentRuntimeResolver,
        ComponentRuntimeResolverError,
    )

    account_info = None
    try:
        from backend.services.shop_account_loader_service import get_shop_account_loader_service

        shop_account_loader = get_shop_account_loader_service()
        shop_payload = await shop_account_loader.load_shop_account_async(request.account_id, db)
        if shop_payload:
            account_info = {
                **shop_payload["compat_account"],
                "main_account_id": shop_payload["main_account"]["main_account_id"],
                "shop_account_id": shop_payload["shop_context"]["shop_account_id"],
            }
    except Exception:
        account_info = None

    if not account_info:
        from backend.services.account_loader_service import get_account_loader_service

        account_loader = get_account_loader_service()
        account_info = await account_loader.load_account_async(request.account_id, db)

    if not account_info:
        raise HTTPException(status_code=404, detail=f"账号 {request.account_id} 不存在或未启用，请先在账号管理中维护")

    task_service = TaskService(db)
    filtered_domains, unsupported_domains = task_service.filter_domains_by_account_capability(
        account_info, request.data_domains
    )

    if not filtered_domains:
        raise HTTPException(
            status_code=400,
            detail=f"账号 {request.account_id} 不支持任何请求的数据域: {', '.join(unsupported_domains)}"
        )

    if unsupported_domains:
        logger.warning(
            f"Filtered out unsupported domains for {request.account_id}: {unsupported_domains}"
        )

    normalized_sub_domains = normalize_domain_subtypes(
        data_domains=filtered_domains,
        sub_domains=request.sub_domains,
    )
    time_selection = normalize_time_selection(
        time_selection=request.time_selection.model_dump(exclude_none=True) if request.time_selection else None,
        date_range=request.date_range,
    )
    effective_granularity = derive_granularity_from_time_selection(
        time_selection,
        request.granularity,
    )
    normalized_date_range = build_date_range_from_time_selection(time_selection)
    normalized_date_range["time_selection"] = time_selection

    try:
        resolver = ComponentRuntimeResolver.from_async_session(db)
        runtime_manifests = await resolver.resolve_task_manifests(
            platform=request.platform,
            data_domains=filtered_domains,
            sub_domains=normalized_sub_domains,
        )
    except ComponentRuntimeResolverError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Stable component not ready: {e}",
        ) from e

    total_domains_count = count_collection_targets(filtered_domains, normalized_sub_domains)

    task = CollectionTask(
        task_id=task_uuid,
        platform=request.platform,
        account=request.account_id,
        status="pending",
        config_id=request.config_id,
        trigger_type="manual",
        data_domains=filtered_domains,
        sub_domains=normalized_sub_domains or None,
        granularity=effective_granularity,
        date_range=normalized_date_range,
        total_domains=total_domains_count,
        completed_domains=[],
        failed_domains=[],
        current_domain=None,
        debug_mode=request.debug_mode,
    )

    db.add(task)
    await db.commit()
    await db.refresh(task)

    log = CollectionTaskLog(
        task_id=task.id,
        level="info",
        message="任务已创建",
        details={
            "trigger": "manual",
            "account": request.account_id,
            "total_domains": total_domains_count,
            "debug_mode": request.debug_mode
        }
    )
    db.add(log)
    await db.commit()

    await _mirror_collection_task(db, task)
    await _mirror_collection_task_log(
        db,
        task.task_id,
        level="info",
        event_type="state_change",
        message=log.message,
        details=log.details,
    )

    logger.info(f"Created collection task: {task_uuid} ({request.platform}/{request.account_id}) - {total_domains_count} domains, debug_mode={request.debug_mode}")

    app = getattr(fastapi_request, "app", None)
    asyncio.create_task(
        _execute_collection_task_background(
            task_id=task_uuid,
            platform=request.platform,
            account_id=request.account_id,
            data_domains=filtered_domains,
            sub_domains=normalized_sub_domains,
            date_range=normalized_date_range,
            granularity=effective_granularity,
            debug_mode=request.debug_mode,
            parallel_mode=request.parallel_mode,
            max_parallel=request.max_parallel,
            runtime_manifests=runtime_manifests,
            app=app,
        )
    )

    return _build_task_response_payload(task)


@router.get("/tasks", response_model=List[TaskResponse])
async def list_tasks(
    platform: Optional[str] = Query(None, description="按平台筛选"),
    status: Optional[str] = Query(None, description="按状态筛选"),
    config_id: Optional[int] = Query(None, description="按配置筛选"),
    limit: int = Query(50, ge=1, le=100, description="返回数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取任务列表"""
    stmt = select(CollectionTask)

    if platform:
        stmt = stmt.where(CollectionTask.platform == platform)

    if status:
        stmt = stmt.where(CollectionTask.status == status)
    if config_id is not None:
        stmt = stmt.where(CollectionTask.config_id == config_id)

    stmt = stmt.order_by(desc(CollectionTask.created_at)).offset(offset).limit(limit)
    result = await db.execute(stmt)
    tasks = result.scalars().all()
    return [_build_task_response_payload(task) for task in tasks]


@router.get("/tasks/verification-items", response_model=List[CollectionVerificationItem])
async def list_verification_items(
    platform: Optional[str] = Query(None, description="按平台筛选"),
    verification_type: Optional[str] = Query(None, description="按验证码类型筛选"),
    account_id: Optional[str] = Query(None, description="按账号筛选"),
    status: Optional[str] = Query("verification_required", description="按状态筛选"),
    db: AsyncSession = Depends(get_async_db),
):
    stmt = select(CollectionTask)

    if platform:
        stmt = stmt.where(CollectionTask.platform == platform)
    if account_id:
        stmt = stmt.where(CollectionTask.account == account_id)
    if status == "verification_required":
        stmt = stmt.where(CollectionTask.status.in_(["verification_required", "paused", "manual_intervention_required"]))
    elif status:
        stmt = stmt.where(CollectionTask.status == status)

    stmt = stmt.order_by(desc(CollectionTask.created_at))
    result = await db.execute(stmt)
    tasks = result.scalars().all()

    items = []
    for task in tasks:
        item = _build_task_verification_item(task)
        if not item:
            continue
        if verification_type and item["verification_type"] != verification_type:
            continue
        items.append(item)
    return items


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str = Path(..., description="任务ID"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取任务详情"""
    result = await db.execute(select(CollectionTask).where(CollectionTask.task_id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return _build_task_response_payload(task)


@router.delete("/tasks/{task_id}", response_model=SuccessResponse[None])
async def cancel_or_delete_task(
    task_id: str = Path(..., description="任务ID"),
    db: AsyncSession = Depends(get_async_db),
):
    """
    取消或删除任务：
    - 终态任务(已完成/失败/已取消/部分成功)：物理删除记录
    - 非终态任务(pending/queued/running/paused)：仅取消(置为 cancelled)，保留记录
    """
    result = await db.execute(select(CollectionTask).where(CollectionTask.task_id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status in TERMINAL_TASK_STATUSES:
        await _mirror_collection_task(db, task)
        await db.delete(task)
        await db.commit()
        await TaskCenterService(db).delete_task(task.task_id)
        logger.info("Deleted terminal task: %s (status=%s)", task_id, task.status)
        return SuccessResponse(success=True, message="任务已删除", data=None)
    else:
        if task.status not in ["pending", "queued", "running", "paused"]:
            raise HTTPException(status_code=400, detail=f"无法取消{task.status}状态的任务")
        prev_status = task.status
        task.status = "cancelled"
        task.error_message = "用户取消"
        log = CollectionTaskLog(
            task_id=task.id,
            level="info",
            message="任务已取消",
            details={"previous_status": prev_status},
        )
        db.add(log)
        await db.commit()
        await _mirror_collection_task(db, task)
        await _mirror_collection_task_log(
            db,
            task.task_id,
            level="info",
            event_type="state_change",
            message=log.message,
            details=log.details,
        )
        logger.info("Cancelled task: %s", task_id)
        return SuccessResponse(success=True, message="任务已取消", data=None)


@router.post("/tasks/{task_id}/retry", response_model=TaskResponse)
async def retry_task(
    task_id: str = Path(..., description="任务ID"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    重试任务

    创建新任务,重新开始整个流程
    """
    result = await db.execute(select(CollectionTask).where(CollectionTask.task_id == task_id))
    original_task = result.scalar_one_or_none()

    if not original_task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if original_task.status not in ["failed", "cancelled"]:
        raise HTTPException(status_code=400, detail=f"无法重试{original_task.status}状态的任务")

    new_task = CollectionTask(
        task_id=str(uuid.uuid4()),
        platform=original_task.platform,
        account=original_task.account,
        status="pending",
        config_id=original_task.config_id,
        trigger_type="retry",
        data_domains=original_task.data_domains,
        sub_domains=original_task.sub_domains,
        granularity=original_task.granularity,
        date_range=original_task.date_range,
        retry_count=original_task.retry_count + 1,
        parent_task_id=original_task.id,
    )

    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)

    log = CollectionTaskLog(
        task_id=new_task.id,
        level="info",
        message="重试任务已创建",
        details={"original_task_id": task_id}
    )
    db.add(log)
    await db.commit()
    await _mirror_collection_task(db, new_task)
    await _mirror_collection_task_log(
        db,
        new_task.task_id,
        level="info",
        event_type="state_change",
        message=log.message,
        details=log.details,
    )

    logger.info(f"Created retry task: {new_task.task_id} (original: {task_id})")
    return _build_task_response_payload(new_task)


@router.post("/tasks/{task_id}/resume", response_model=TaskResponse)
async def resume_task(
    task_id: str = Path(..., description="任务ID"),
    body: Optional[ResumeTaskRequest] = None,
    request: Request = None,
    db: AsyncSession = Depends(get_async_db),
):
    """
    继续任务(验证码恢复)。
    仅当任务处于 verification_required/paused 且为「等待验证」时接受请求体中的 captcha_code 或 otp，
    写入 Redis 供执行器在同一 page 内填入后继续；否则返回 4xx。
    """
    result = await db.execute(select(CollectionTask).where(CollectionTask.task_id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status not in ("verification_required", "paused"):
        raise HTTPException(
            status_code=400,
            detail="验证已超时或任务已结束，请重新发起采集",
        )

    payload = body or ResumeTaskRequest()
    value, response_payload = extract_resume_submission(
        captcha_code=payload.captcha_code,
        otp=payload.otp,
        manual_completed=payload.manual_completed,
    )
    if not response_payload:
        raise HTTPException(status_code=400, detail="请提供 captcha_code、otp 或 manual_completed")

    redis_client = None
    if request and getattr(request, "app", None):
        redis_client = getattr(request.app.state, "redis", None)
    if not redis_client:
        raise HTTPException(
            status_code=503,
            detail="验证码恢复需要 Redis，当前未配置或不可用",
        )

    key = f"{CAPTCHA_REDIS_KEY_PREFIX}{task_id}"
    try:
        await redis_client.set(key, value, ex=600)
    except Exception as e:
        logger.error(f"Resume task {task_id}: Redis set failed: {e}")
        raise HTTPException(status_code=503, detail="写入验证码失败，请稍后重试")

    log = CollectionTaskLog(
        task_id=task.id,
        level="info",
        message="用户已提交验证码，等待执行器继续",
        details={"previous_status": task.status},
    )
    task.status = "verification_submitted"
    db.add(log)
    await db.commit()
    refresh_result = getattr(db, "refresh", None)
    if refresh_result is not None:
        maybe_refresh = refresh_result(task)
        if inspect.isawaitable(maybe_refresh):
            await maybe_refresh
    await _mirror_collection_task(db, task)
    await _mirror_collection_task_log(
        db,
        task.task_id,
        level="info",
        event_type="verification",
        message=log.message,
        details=log.details,
    )

    logger.info(f"Resumed task: {task_id} (verification submitted)")
    return _build_task_response_payload(task)


@router.get("/tasks/{task_id}/logs", response_model=List[TaskLogResponse])
async def get_task_logs(
    task_id: str = Path(..., description="任务ID"),
    level: Optional[str] = Query(None, description="按日志级别筛选"),
    limit: int = Query(100, ge=1, le=500, description="返回数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取任务日志"""
    result = await db.execute(select(CollectionTask).where(CollectionTask.task_id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    stmt = select(CollectionTaskLog).where(CollectionTaskLog.task_id == task.id)

    if level:
        stmt = stmt.where(CollectionTaskLog.level == level)

    stmt = stmt.order_by(CollectionTaskLog.timestamp).limit(limit)
    result = await db.execute(stmt)
    logs = result.scalars().all()
    return logs


@router.get("/tasks/{task_id}/screenshot")
async def get_task_screenshot(
    task_id: str = Path(..., description="任务ID"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取任务截图(验证码截图)

    返回任务的验证码截图文件(如果存在)
    """
    from pathlib import Path as PathLib

    result = await db.execute(select(CollectionTask).where(CollectionTask.task_id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    screenshot_path = task.verification_screenshot

    if not screenshot_path:
        raise HTTPException(status_code=404, detail="任务没有截图")

    if not PathLib(screenshot_path).is_absolute():
        project_root = PathLib(__file__).parent.parent.parent
        screenshot_path = str(project_root / screenshot_path)

    if not os.path.exists(screenshot_path):
        raise HTTPException(status_code=404, detail=f"截图文件不存在: {screenshot_path}")

    return FileResponse(
        path=screenshot_path,
        media_type="image/png",
        filename=f"task_{task_id}_screenshot.png"
    )


# ============================================================
# 历史和统计 API
# ============================================================

@router.get("/history", response_model=TaskHistoryResponse)
async def get_history(
    platform: Optional[str] = Query(None, description="按平台筛选"),
    status: Optional[str] = Query(None, description="按状态筛选"),
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取采集历史记录(分页)"""
    from sqlalchemy import func

    conditions = []

    if platform:
        conditions.append(CollectionTask.platform == platform)

    if status:
        conditions.append(CollectionTask.status == status)

    if start_date:
        conditions.append(CollectionTask.created_at >= datetime.combine(start_date, datetime.min.time()))

    if end_date:
        conditions.append(CollectionTask.created_at <= datetime.combine(end_date, datetime.max.time()))

    count_stmt = select(func.count(CollectionTask.id))
    if conditions:
        count_stmt = count_stmt.where(*conditions)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0

    stmt = select(CollectionTask)
    if conditions:
        stmt = stmt.where(*conditions)
    stmt = stmt.order_by(desc(CollectionTask.created_at)).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    tasks = result.scalars().all()

    return TaskHistoryResponse(
        data=[_build_task_response_payload(task) for task in tasks],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size
    )


@router.get("/history/stats", response_model=TaskStatsResponse)
async def get_history_stats(
    days: int = Query(7, ge=1, le=30, description="统计天数"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取采集统计数据"""
    from sqlalchemy import func
    start_date = datetime.now() - timedelta(days=days)

    status_stmt = select(
        CollectionTask.status,
        func.count(CollectionTask.id).label("count")
    ).where(
        CollectionTask.created_at >= start_date
    ).group_by(CollectionTask.status)
    status_result = await db.execute(status_stmt)
    status_stats = status_result.all()

    platform_stmt = select(
        CollectionTask.platform,
        func.count(CollectionTask.id).label("count")
    ).where(
        CollectionTask.created_at >= start_date
    ).group_by(CollectionTask.platform)
    platform_result = await db.execute(platform_stmt)
    platform_stats = platform_result.all()

    status_dict = {s[0]: s[1] for s in status_stats}
    total = sum(status_dict.values()) or 1
    completed_count = status_dict.get("completed", 0)
    failed_count = status_dict.get("failed", 0)
    running_count = status_dict.get("running", 0)
    queued_count = status_dict.get("queued", 0)
    success_rate = round(completed_count / total * 100, 2)

    daily_stats = []
    for i in range(days):
        day = (datetime.now() - timedelta(days=i)).date()
        day_stmt = select(CollectionTask).where(
            func.date(CollectionTask.created_at) == day
        )
        day_result = await db.execute(day_stmt)
        day_tasks = day_result.scalars().all()

        day_total = len(day_tasks)
        day_completed = sum(1 for t in day_tasks if t.status == "completed")
        day_failed = sum(1 for t in day_tasks if t.status == "failed")
        day_rate = round(day_completed / day_total * 100, 2) if day_total > 0 else 0

        daily_stats.append(DailyStats(
            date=day,
            total=day_total,
            completed=day_completed,
            failed=day_failed,
            success_rate=day_rate
        ))

    return TaskStatsResponse(
        total_tasks=total,
        completed=completed_count,
        failed=failed_count,
        running=running_count,
        queued=queued_count,
        success_rate=success_rate,
        daily_stats=daily_stats
    )


# ============================================================
# 步骤可观测：状态回调(独立 session 写库，不阻塞执行器)
# ============================================================

async def _collection_step_status_callback(
    task_id: str,
    progress: int,
    message: str,
    current_domain: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """
    采集步骤状态回调：更新任务进度并可选写入步骤日志。
    使用独立 AsyncSession 每次写后 commit，不与后台任务 session 混用。
    异常仅打日志不 re-raise，避免回调失败中断采集。
    """
    from backend.models.database import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(CollectionTask).where(CollectionTask.task_id == task_id))
            task = result.scalar_one_or_none()
            if not task:
                return
            task.progress = progress
            task.current_step = message
            if current_domain is not None:
                task.current_domain = current_domain
            if details is not None:
                log_level = "error" if details.get("error") else "info"
                log = CollectionTaskLog(task_id=task.id, level=log_level, message=message, details=details)
                session.add(log)
            await session.commit()
            await _mirror_collection_task(session, task)
            if details is not None:
                await _mirror_collection_task_log(
                    session,
                    task.task_id,
                    level=log_level,
                    event_type="progress",
                    message=message,
                    details=details,
                )
            await connection_manager.send_progress(
                task_id,
                progress,
                message,
                status=getattr(task, "status", None) or "running",
            )
    except Exception as e:
        logger.error(f"Step status callback failed for task {task_id}: {e}")


async def _is_collection_task_cancelled(task_id: str) -> bool:
    """检测任务是否已被用户取消(供 executor is_cancelled_callback)."""
    from backend.models.database import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(CollectionTask).where(CollectionTask.task_id == task_id))
            task = result.scalar_one_or_none()
            return task is not None and task.status == "cancelled"
    except Exception as e:
        logger.error(f"Cancel check failed for task {task_id}: {e}")
        return False


# ============================================================
# 后台任务执行(v4.7.0)
# ============================================================

async def _on_verification_required(
    task_id: str,
    verification_type: str,
    screenshot_path: Optional[str],
    app: Any,
) -> Optional[str]:
    """
    验证码需要时的回调：持久化到任务表并置 paused，然后轮询 Redis 等待用户回传，超时返回 None。
    返回用户提交的 captcha_code/otp 或 None(超时)。
    """
    from backend.models.database import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(CollectionTask).where(CollectionTask.task_id == task_id))
            task = result.scalar_one_or_none()
            if task:
                task.verification_type = verification_type
                task.verification_screenshot = screenshot_path
                task.status = "verification_required"
                await session.commit()
                await _mirror_collection_task(session, task)
                await connection_manager.send_verification_required(
                    task_id,
                    verification_type,
                    screenshot_path,
                )
    except Exception as e:
        logger.error(f"Verification persist failed for task {task_id}: {e}")
    redis_client = getattr(app, "state", None) and getattr(app.state, "redis", None) if app else None
    if not redis_client:
        logger.warning(f"Task {task_id}: Redis not available, verification wait will timeout immediately")
        await asyncio.sleep(min(5, VERIFICATION_WAIT_TIMEOUT))
        return None
    key = f"{CAPTCHA_REDIS_KEY_PREFIX}{task_id}"
    loop = asyncio.get_running_loop()
    deadline = loop.time() + VERIFICATION_WAIT_TIMEOUT
    while loop.time() < deadline:
        try:
            val = await redis_client.get(key)
            if val is not None:
                try:
                    await redis_client.delete(key)
                except Exception:
                    pass
                try:
                    async with AsyncSessionLocal() as session:
                        result = await session.execute(
                            select(CollectionTask).where(CollectionTask.task_id == task_id)
                        )
                        task = result.scalar_one_or_none()
                        if task:
                            task.status = "running"
                            await session.commit()
                            await _mirror_collection_task(session, task)
                except Exception as e:
                    logger.warning(f"Task {task_id}: failed to switch status back to running after verification: {e}")
                return val
        except Exception as e:
            logger.debug(f"Redis get during verification wait: {e}")
        await asyncio.sleep(VERIFICATION_POLL_INTERVAL)
    logger.info(f"Task {task_id}: verification wait timed out after {VERIFICATION_WAIT_TIMEOUT}s")
    return None


async def _execute_collection_task_background(
    task_id: str,
    platform: str,
    account_id: str,
    data_domains: List[str],
    sub_domains: Optional[List[str]],
    date_range: Dict[str, str],
    granularity: str,
    debug_mode: bool,
    parallel_mode: bool,
    max_parallel: int,
    runtime_manifests: Optional[Dict[str, Any]] = None,
    app: Any = None,
):
    """
    后台执行采集任务(v4.7.0 + Phase 9.1)
    """
    from backend.models.database import AsyncSessionLocal
    from modules.apps.collection_center.executor_v2 import CollectionExecutorV2

    async def _verification_callback(t_id: str, v_type: str, s_path: Optional[str]) -> Optional[str]:
        return await _on_verification_required(t_id, v_type, s_path, app)

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(CollectionTask).where(CollectionTask.task_id == task_id))
            task = result.scalar_one_or_none()
            if not task:
                logger.error(f"Task {task_id} not found in database")
                return

            task.status = "running"
            task.started_at = datetime.now(timezone.utc)
            await db.commit()
            await _mirror_collection_task(db, task)

            try:
                account = None
                try:
                    from backend.services.shop_account_loader_service import get_shop_account_loader_service

                    shop_account_loader = get_shop_account_loader_service()
                    shop_payload = await shop_account_loader.load_shop_account_async(account_id, db)
                    if shop_payload:
                        account = {
                            **shop_payload["compat_account"],
                            "main_account_id": shop_payload["main_account"]["main_account_id"],
                            "shop_account_id": shop_payload["shop_context"]["shop_account_id"],
                        }
                except Exception:
                    account = None

                if not account:
                    from backend.services.account_loader_service import get_account_loader_service

                    account_loader = get_account_loader_service()
                    account = await account_loader.load_account_async(account_id, db)

                if not account:
                    raise ValueError(f"Account {account_id} not found or disabled")

            except Exception as e:
                logger.error(f"Failed to load account {account_id}: {e}")
                task.status = "failed"
                task.error_message = f"账号加载失败: {str(e)}"
                task.completed_at = datetime.now(timezone.utc)
                await db.commit()
                await _mirror_collection_task(db, task)
                await connection_manager.send_complete(
                    task_id,
                    "failed",
                    files_collected=getattr(task, "files_collected", 0) or 0,
                    error_message=task.error_message,
                )
                return

            executor = CollectionExecutorV2(
                status_callback=_collection_step_status_callback,
                is_cancelled_callback=_is_collection_task_cancelled,
                verification_required_callback=_verification_callback,
            )

            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                from modules.apps.collection_center.browser_config_helper import get_browser_launch_args

                browser = await p.chromium.launch(**get_browser_launch_args(debug_mode=debug_mode))
                try:
                    if parallel_mode:
                        logger.info(f"Task {task_id}: Using PARALLEL execution mode (max_parallel={max_parallel})")
                        result = await executor.execute_parallel_domains(
                            task_id=task_id,
                            platform=platform,
                            account_id=account_id,
                            account=account,
                            data_domains=data_domains,
                            date_range=date_range,
                            granularity=granularity,
                            browser=browser,
                            max_parallel=max_parallel,
                            debug_mode=debug_mode,
                            runtime_manifests=runtime_manifests,
                        )
                    else:
                        result = await executor.execute(
                            task_id=task_id,
                            platform=platform,
                            account_id=account_id,
                            account=account,
                            data_domains=data_domains,
                            sub_domains=sub_domains,
                            date_range=date_range,
                            granularity=granularity,
                            browser=browser,
                            debug_mode=debug_mode,
                            runtime_manifests=runtime_manifests,
                        )

                    task.status = result.status
                    task.progress = 100 if result.status in ["completed", "partial_success"] else 0
                    task.files_collected = result.files_collected
                    task.error_message = result.error_message
                    task.completed_at = datetime.now(timezone.utc)
                    task.duration_seconds = result.duration_seconds
                    task.completed_domains = result.completed_domains
                    task.failed_domains = result.failed_domains
                    await db.commit()
                    await _mirror_collection_task(db, task)
                    await connection_manager.send_complete(
                        task_id,
                        result.status,
                        files_collected=result.files_collected,
                        error_message=result.error_message,
                    )
                    logger.info(f"Task {task_id} completed: {result.status}, files={result.files_collected}")
                finally:
                    await browser.close()

        except Exception as e:
            logger.exception(f"Background task {task_id} failed: {e}")

            try:
                result = await db.execute(select(CollectionTask).where(CollectionTask.task_id == task_id))
                task = result.scalar_one_or_none()
                if task:
                    task.status = "failed"
                    task.error_message = str(e)
                    task.completed_at = datetime.now(timezone.utc)
                    await db.commit()
                    await _mirror_collection_task(db, task)
                    await connection_manager.send_complete(
                        task_id,
                        "failed",
                        files_collected=getattr(task, "files_collected", 0) or 0,
                        error_message=str(e),
                    )
            except Exception as db_error:
                logger.error(f"Failed to update task status: {db_error}")
