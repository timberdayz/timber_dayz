"""
Collection scheduling and health APIs.
"""

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import require_admin
from backend.models.database import get_async_db
from backend.schemas.collection import (
    CollectionConfigRunResponse,
    CronPresetsResponse,
    CronPresetItem,
    CronValidateRequest,
    CronValidationResponse,
    GranularityScheduleResponse,
    GranularityScheduleUpdateRequest,
    HealthCheckResponse,
    ScheduleInfoResponse,
    ScheduledJobInfo,
    ScheduledJobsResponse,
    ScheduleResponse,
    ScheduleUpdateRequest,
)
from backend.schemas.common import SuccessResponse
from modules.core.db import CollectionConfig, CollectionConfigRun
from modules.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["collection-schedule"], dependencies=[Depends(require_admin)])

GRANULARITY_SCHEDULE_PRESETS = {
    "daily": {
        "cron": "0 7 * * *",
        "description": "每天 07:00 自动采集昨天",
    },
    "weekly": {
        "cron": "0 9 * * 1",
        "description": "每周一 09:00 自动采集上周",
    },
    "monthly": {
        "cron": "0 9 1 * *",
        "description": "每月 1 日 09:00 自动采集上月",
    },
}


def _select_current_configs(configs: list[CollectionConfig]) -> list[CollectionConfig]:
    grouped: dict[tuple[str, str, str], list[CollectionConfig]] = {}
    for config in configs:
        key = (str(config.platform or ""), str(config.main_account_id or ""), str(config.granularity or ""))
        grouped.setdefault(key, []).append(config)

    selected: list[CollectionConfig] = []
    for bucket in grouped.values():
        bucket.sort(
            key=lambda item: (
                0 if str(getattr(item, "batch_status", "") or "").lower() == "active" else 1,
                -(getattr(item, "updated_at", None).timestamp() if getattr(item, "updated_at", None) else 0),
                -(getattr(item, "id", 0) or 0),
            )
        )
        selected.append(bucket[0])
    return selected


def _build_granularity_schedule_response(
    granularity: str,
    configs: list[CollectionConfig],
) -> GranularityScheduleResponse:
    preset = GRANULARITY_SCHEDULE_PRESETS[granularity]
    total = len(configs)
    enabled_configs = [
        config
        for config in configs
        if config.is_active
        and config.schedule_enabled
        and str(config.schedule_cron or "").strip() == preset["cron"]
    ]
    other_scheduled_configs = [
        config
        for config in configs
        if config.is_active
        and config.schedule_enabled
        and str(config.schedule_cron or "").strip() != preset["cron"]
    ]
    return GranularityScheduleResponse(
        granularity=granularity,
        enabled=total > 0 and len(enabled_configs) == total,
        cron=preset["cron"],
        description=preset["description"],
        affected_config_count=total,
        enabled_config_count=len(enabled_configs),
        is_mixed=bool(other_scheduled_configs) or (0 < len(enabled_configs) < total),
    )


@router.get("/config-runs", response_model=list[CollectionConfigRunResponse])
async def list_config_runs(
    status: str | None = Query(None, description="Filter by config run status"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
):
    stmt = select(CollectionConfigRun)
    if status:
        stmt = stmt.where(CollectionConfigRun.status == status)
    stmt = stmt.order_by(
        CollectionConfigRun.created_at.desc(),
        CollectionConfigRun.id.desc(),
    ).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/config-runs/{run_id}", response_model=CollectionConfigRunResponse)
async def get_config_run(
    run_id: str,
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        select(CollectionConfigRun).where(CollectionConfigRun.run_id == run_id)
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="config run not found")
    return run


@router.delete("/config-runs/{run_id}", response_model=SuccessResponse[None])
async def cancel_config_run(
    run_id: str,
    db: AsyncSession = Depends(get_async_db),
):
    from backend.services.collection_config_run_service import CollectionConfigRunService

    service = CollectionConfigRunService(db)
    try:
        await service.cancel_run_by_run_id(run_id)
    except ValueError as exc:
        detail = str(exc)
        if detail.startswith("CollectionConfigRun not found:"):
            raise HTTPException(status_code=404, detail="config run not found") from exc
        if detail == "only queued config runs can be cancelled":
            raise HTTPException(status_code=409, detail=detail) from exc
        raise HTTPException(status_code=400, detail=detail) from exc
    return SuccessResponse(success=True, message="config run cancelled", data=None)


@router.get(
    "/schedule/granularity/{granularity}",
    response_model=GranularityScheduleResponse,
)
async def get_granularity_schedule(
    granularity: str = Path(..., pattern="^(daily|weekly|monthly)$"),
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        select(CollectionConfig).where(
            CollectionConfig.granularity == granularity,
            CollectionConfig.is_active == True,
        )
    )
    configs = _select_current_configs(list(result.scalars().all()))
    return _build_granularity_schedule_response(granularity, configs)


@router.post(
    "/schedule/granularity/{granularity}",
    response_model=GranularityScheduleResponse,
)
async def update_granularity_schedule(
    payload: GranularityScheduleUpdateRequest,
    granularity: str = Path(..., pattern="^(daily|weekly|monthly)$"),
    db: AsyncSession = Depends(get_async_db),
):
    from backend.services.collection_scheduler import (
        APSCHEDULER_AVAILABLE,
        CollectionScheduler,
    )

    if not APSCHEDULER_AVAILABLE:
        raise HTTPException(status_code=503, detail="scheduled collection service unavailable")

    preset = GRANULARITY_SCHEDULE_PRESETS[granularity]
    result = await db.execute(
        select(CollectionConfig).where(
            CollectionConfig.granularity == granularity,
            CollectionConfig.is_active == True,
        )
    )
    configs = _select_current_configs(list(result.scalars().all()))

    scheduler = CollectionScheduler.get_instance()
    for config in configs:
        if payload.schedule_enabled:
            config.schedule_enabled = True
            config.schedule_cron = preset["cron"]
            await scheduler.add_schedule(config.id, preset["cron"])
        else:
            config.schedule_enabled = False
            config.schedule_cron = None
            await scheduler.remove_schedule(config.id)

    await db.commit()
    return _build_granularity_schedule_response(granularity, configs)


@router.post("/configs/{config_id}/schedule", response_model=ScheduleResponse)
async def update_config_schedule(
    config_id: int,
    request: ScheduleUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
):
    from backend.services.collection_scheduler import APSCHEDULER_AVAILABLE, CollectionScheduler

    if not APSCHEDULER_AVAILABLE:
        raise HTTPException(status_code=503, detail="scheduled collection service unavailable")

    result = await db.execute(select(CollectionConfig).where(CollectionConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="config not found")

    if request.schedule_enabled and request.schedule_cron:
        if not CollectionScheduler.validate_cron_expression(request.schedule_cron):
            raise HTTPException(status_code=400, detail="invalid cron expression")

    config.schedule_enabled = request.schedule_enabled
    config.schedule_cron = request.schedule_cron if request.schedule_enabled else None
    await db.commit()

    scheduler = CollectionScheduler.get_instance()
    if request.schedule_enabled and request.schedule_cron:
        await scheduler.add_schedule(config_id, request.schedule_cron)
    else:
        await scheduler.remove_schedule(config_id)

    job_info = scheduler.get_job_info(config_id) if request.schedule_enabled else None
    return ScheduleResponse(
        message=f"schedule {'enabled' if request.schedule_enabled else 'disabled'}",
        config_id=config_id,
        job_id=job_info.get("job_id") if job_info else None,
        next_run_time=job_info.get("next_run_time") if job_info else None,
    )


@router.get("/configs/{config_id}/schedule", response_model=ScheduleInfoResponse)
async def get_config_schedule(
    config_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    from backend.services.collection_scheduler import APSCHEDULER_AVAILABLE, CollectionScheduler

    result = await db.execute(select(CollectionConfig).where(CollectionConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="config not found")

    next_run_time = None
    job_id = None
    if APSCHEDULER_AVAILABLE and config.schedule_enabled:
        try:
            scheduler = CollectionScheduler.get_instance()
            job_info = scheduler.get_job_info(config_id)
            if job_info:
                next_run_time = job_info.get("next_run_time")
                job_id = job_info.get("job_id")
        except Exception as exc:
            logger.warning("Failed to get job info for config %s: %s", config_id, exc)

    return ScheduleInfoResponse(
        enabled=config.schedule_enabled,
        cron=config.schedule_cron,
        next_run_time=next_run_time,
        job_id=job_id,
    )


@router.post("/schedule/validate", response_model=CronValidationResponse)
async def validate_cron_expression(request: CronValidateRequest):
    from backend.services.collection_scheduler import APSCHEDULER_AVAILABLE, CollectionScheduler

    if not APSCHEDULER_AVAILABLE:
        return CronValidationResponse(valid=False, error="APScheduler not installed")

    is_valid = CollectionScheduler.validate_cron_expression(request.cron_expression)
    return CronValidationResponse(
        valid=is_valid,
        error=None if is_valid else "invalid cron expression",
        description=CollectionScheduler.get_cron_description(request.cron_expression) if is_valid else None,
    )


@router.get("/schedule/presets", response_model=CronPresetsResponse)
async def get_cron_presets():
    from backend.services.collection_scheduler import CRON_PRESETS, CollectionScheduler

    presets = [
        CronPresetItem(
            name=name,
            cron=cron,
            description=CollectionScheduler.get_cron_description(cron),
        )
        for name, cron in CRON_PRESETS.items()
    ]
    return CronPresetsResponse(presets=presets)


@router.get("/schedule/jobs", response_model=ScheduledJobsResponse)
async def list_scheduled_jobs():
    from backend.services.collection_scheduler import APSCHEDULER_AVAILABLE, CollectionScheduler

    if not APSCHEDULER_AVAILABLE:
        return ScheduledJobsResponse(jobs=[], total=0, error="scheduler unavailable")

    try:
        scheduler = CollectionScheduler.get_instance()
        jobs = [
            ScheduledJobInfo(
                job_id=item.get("job_id"),
                name=item.get("name"),
                next_run_time=item.get("next_run_time"),
                trigger=item.get("trigger", "cron"),
            )
            for item in scheduler.get_all_jobs()
        ]
        return ScheduledJobsResponse(jobs=jobs, total=len(jobs))
    except Exception as exc:
        logger.error("Failed to list scheduled jobs: %s", exc)
        return ScheduledJobsResponse(jobs=[], total=0, error=str(exc))


@router.get("/health", response_model=HealthCheckResponse)
async def health_check(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    from backend.schemas.collection import BrowserPoolStatus
    from backend.services.collection_scheduler import APSCHEDULER_AVAILABLE
    from backend.services.task_service import TaskService

    running_count = 0
    queued_count = 0
    running_config_runs = 0
    queued_config_runs = 0
    active_config_run = None

    try:
        result = await db.execute(
            text(
                """
                SELECT status, COUNT(*) as count
                FROM collection_tasks
                WHERE status IN ('running', 'queued')
                GROUP BY status
                """
            )
        )
        for row in result:
            if row[0] == "running":
                running_count = row[1]
            elif row[0] == "queued":
                queued_count = row[1]
    except Exception as exc:
        logger.warning("Health check task query failed: %s", exc)

    try:
        config_run_rows = (
            await db.execute(
                select(CollectionConfigRun).where(
                    CollectionConfigRun.status.in_(["running", "queued"])
                )
            )
        ).scalars().all()
        for row in config_run_rows:
            if row.status == "running":
                running_config_runs += 1
                if active_config_run is None:
                    active_config_run = {
                        "id": row.id,
                        "run_id": row.run_id,
                        "config_id": row.config_id,
                        "main_account_id": row.main_account_id,
                        "platform": row.platform,
                        "trigger_type": row.trigger_type,
                        "status": row.status,
                        "started_at": row.started_at,
                    }
            elif row.status == "queued":
                queued_config_runs += 1
    except Exception as exc:
        logger.warning("Health check config run query failed: %s", exc)

    db_status = "ok"
    try:
        await db.execute(text("SELECT 1"))
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

    queue_runner = getattr(request.app.state, "collection_queue_runner", None)
    queue_runner_task = getattr(queue_runner, "_task", None)
    queue_runner_status = "running" if queue_runner_task and not queue_runner_task.done() else "stopped"

    return HealthCheckResponse(
        status="healthy",
        running_tasks=running_count,
        queued_tasks=queued_count,
        running_config_runs=running_config_runs,
        queued_config_runs=queued_config_runs,
        active_config_run=active_config_run,
        browser_pool=BrowserPoolStatus(
            active=running_count,
            max_allowed=TaskService.MAX_CONCURRENT_TASKS,
        ),
        database=db_status,
        scheduler=scheduler_status,
        queue_runner=queue_runner_status,
        can_consume_queue=queue_runner_status == "running",
    )
