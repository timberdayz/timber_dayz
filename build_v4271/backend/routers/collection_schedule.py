"""
数据采集模块 - 调度管理与健康检查 API

拆分自 collection.py，包含定时调度 CRUD、Cron 验证、预设、任务列表和健康检查端点。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models.database import get_async_db
from modules.core.db import CollectionConfig
from modules.core.logger import get_logger
from backend.schemas.collection import (
    ScheduleUpdateRequest,
    CronValidateRequest,
    ScheduleResponse,
    ScheduleInfoResponse,
    CronValidationResponse,
    CronPresetsResponse,
    ScheduledJobsResponse,
    HealthCheckResponse,
)

logger = get_logger(__name__)

router = APIRouter(tags=["数据采集-调度"])


# ============================================================
# 调度管理 API
# ============================================================

@router.post("/configs/{config_id}/schedule", response_model=ScheduleResponse)
async def update_config_schedule(
    config_id: int,
    request: ScheduleUpdateRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    更新配置的定时设置

    启用/禁用定时采集,设置Cron表达式
    """
    from backend.services.collection_scheduler import CollectionScheduler, APSCHEDULER_AVAILABLE

    if not APSCHEDULER_AVAILABLE:
        raise HTTPException(status_code=503, detail="定时调度服务未安装")

    result = await db.execute(select(CollectionConfig).where(CollectionConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")

    if request.schedule_enabled and request.schedule_cron:
        if not CollectionScheduler.validate_cron_expression(request.schedule_cron):
            raise HTTPException(status_code=400, detail="无效的Cron表达式")

    config.schedule_enabled = request.schedule_enabled
    config.schedule_cron = request.schedule_cron if request.schedule_enabled else None
    await db.commit()

    try:
        scheduler = CollectionScheduler.get_instance()

        if request.schedule_enabled and request.schedule_cron:
            await scheduler.add_schedule(config_id, request.schedule_cron)
            action = "enabled"
        else:
            await scheduler.remove_schedule(config_id)
            action = "disabled"

        logger.info(f"Schedule {action} for config {config_id}")

        next_run_time = None
        job_id = None
        if request.schedule_enabled:
            job_info = scheduler.get_job_info(config_id)
            if job_info:
                next_run_time = job_info.get("next_run_time")
                job_id = job_info.get("job_id")

        return ScheduleResponse(
            message=f"定时任务已{'启用' if request.schedule_enabled else '禁用'}",
            config_id=config_id,
            job_id=job_id,
            next_run_time=next_run_time
        )

    except Exception as e:
        logger.error(f"Failed to update schedule for config {config_id}: {e}")
        raise HTTPException(status_code=500, detail=f"更新调度失败: {str(e)}")


@router.get("/configs/{config_id}/schedule", response_model=ScheduleInfoResponse)
async def get_config_schedule(
    config_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取配置的定时状态

    返回下次执行时间、历史执行记录等
    """
    from backend.services.collection_scheduler import CollectionScheduler, APSCHEDULER_AVAILABLE

    result = await db.execute(select(CollectionConfig).where(CollectionConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")

    next_run_time = None
    job_id = None

    if APSCHEDULER_AVAILABLE and config.schedule_enabled:
        try:
            scheduler = CollectionScheduler.get_instance()
            job_info = scheduler.get_job_info(config_id)
            if job_info:
                next_run_time = job_info.get("next_run_time")
                job_id = job_info.get("job_id")
        except Exception as e:
            logger.warning(f"Failed to get job info for config {config_id}: {e}")

    return ScheduleInfoResponse(
        enabled=config.schedule_enabled,
        cron=config.schedule_cron,
        next_run_time=next_run_time,
        job_id=job_id
    )


@router.post("/schedule/validate", response_model=CronValidationResponse)
async def validate_cron_expression(request: CronValidateRequest):
    """
    验证Cron表达式

    返回是否有效及人类可读描述
    """
    from backend.services.collection_scheduler import CollectionScheduler, APSCHEDULER_AVAILABLE

    if not APSCHEDULER_AVAILABLE:
        return CronValidationResponse(
            valid=False,
            error="APScheduler未安装"
        )

    is_valid = CollectionScheduler.validate_cron_expression(request.cron_expression)

    return CronValidationResponse(
        valid=is_valid,
        error=None if is_valid else "无效的Cron表达式格式",
        description=CollectionScheduler.get_cron_description(request.cron_expression) if is_valid else None
    )


@router.get("/schedule/presets", response_model=CronPresetsResponse)
async def get_cron_presets():
    """
    获取预定义的Cron表达式

    返回常用的定时配置选项
    """
    from backend.services.collection_scheduler import CRON_PRESETS, CollectionScheduler
    from backend.schemas.collection import CronPresetItem

    presets = []
    for name, cron in CRON_PRESETS.items():
        presets.append(CronPresetItem(
            name=name,
            cron=cron,
            description=CollectionScheduler.get_cron_description(cron)
        ))

    return CronPresetsResponse(presets=presets)


@router.get("/schedule/jobs", response_model=ScheduledJobsResponse)
async def list_scheduled_jobs():
    """
    获取所有定时任务

    返回当前所有已注册的定时任务
    """
    from backend.services.collection_scheduler import CollectionScheduler, APSCHEDULER_AVAILABLE
    from backend.schemas.collection import ScheduledJobInfo

    if not APSCHEDULER_AVAILABLE:
        return ScheduledJobsResponse(
            jobs=[],
            total=0,
            error="调度服务未安装"
        )

    try:
        scheduler = CollectionScheduler.get_instance()
        jobs_data = scheduler.get_all_jobs()

        jobs = [
            ScheduledJobInfo(
                job_id=j.get("job_id"),
                name=j.get("name"),
                next_run_time=j.get("next_run_time"),
                trigger=j.get("trigger", "cron")
            )
            for j in jobs_data
        ]

        return ScheduledJobsResponse(
            jobs=jobs,
            total=len(jobs)
        )
    except Exception as e:
        logger.error(f"Failed to list scheduled jobs: {e}")
        return ScheduledJobsResponse(
            jobs=[],
            total=0,
            error=str(e)
        )


# ============================================================
# 健康检查
# ============================================================

@router.get("/health", response_model=HealthCheckResponse)
async def health_check(db: AsyncSession = Depends(get_async_db)):
    """
    采集模块健康检查

    返回:
    - 运行中任务数
    - 排队任务数
    - 浏览器池状态
    - 数据库状态
    - 调度器状态
    """
    from backend.services.collection_scheduler import APSCHEDULER_AVAILABLE
    from backend.schemas.collection import BrowserPoolStatus

    running_count = 0
    queued_count = 0
    try:
        from sqlalchemy import text
        result = await db.execute(text("""
            SELECT status, COUNT(*) as count 
            FROM collection_tasks 
            WHERE status IN ('running', 'queued')
            GROUP BY status
        """))
        for row in result:
            if row[0] == "running":
                running_count = row[1]
            elif row[0] == "queued":
                queued_count = row[1]
    except Exception as e:
        logger.warning(f"Health check task query failed (migration pending?): {e}")

    from backend.services.task_service import TaskService
    max_concurrent = TaskService.MAX_CONCURRENT_TASKS

    db_status = "ok"
    try:
        from sqlalchemy import text as _text
        await db.execute(_text("SELECT 1"))
    except Exception:
        db_status = "error"

    scheduler_status = "not_installed" if not APSCHEDULER_AVAILABLE else "ok"
    if APSCHEDULER_AVAILABLE:
        try:
            from backend.services.collection_scheduler import CollectionScheduler
            scheduler = CollectionScheduler.get_instance()
            if not scheduler:
                scheduler_status = "error"
        except Exception:
            scheduler_status = "error"

    return HealthCheckResponse(
        status="healthy",
        running_tasks=running_count,
        queued_tasks=queued_count,
        browser_pool=BrowserPoolStatus(
            active=running_count,
            max_allowed=max_concurrent
        ),
        database=db_status,
        scheduler=scheduler_status
    )
