from __future__ import annotations

import asyncio

from backend.celery_app import celery_app
from backend.models.database import AsyncSessionLocal, reset_async_engine_pool_for_new_loop
from backend.services.data_pipeline.inventory_age_refresh_service import InventoryAgeRefreshService
from backend.services.data_pipeline.refresh_queue_service import RefreshQueueService
from backend.services.data_pipeline.refresh_runner import (
    execute_refresh_plan,
    extract_failed_targets,
    extract_refresh_status,
    extract_run_id,
)
from modules.core.logger import get_logger

logger = get_logger(__name__)
REFRESH_QUEUE_RUNNING_TIMEOUT_SECONDS = 10 * 60


async def _async_process_refresh_queue_task() -> dict:
    db = AsyncSessionLocal()
    try:
        queue_service = RefreshQueueService(db)
        recovered_count = await queue_service.recover_stale_running_tasks(
            timeout_seconds=REFRESH_QUEUE_RUNNING_TIMEOUT_SECONDS
        )
        if recovered_count:
            logger.warning(
                "[RefreshQueue] recovered %s stale running refresh tasks",
                recovered_count,
            )
        task = await queue_service.claim_next_refresh_task()
        if task is None:
            return {"status": "skipped", "reason": "no_pending_refresh_queue_task"}

        try:
            refresh_result = await execute_refresh_plan(
                db,
                targets=list(task.targets_json or []),
                pipeline_name=task.pipeline_name,
                trigger_source=getattr(task, "trigger_type", "data_ingested"),
                context=dict(task.context_json or {}),
                continue_on_error=True,
                max_attempts=2,
                retry_backoff_seconds=0.1,
            )
            run_id = extract_run_id(refresh_result)
            refresh_status = extract_refresh_status(refresh_result)
            failed_targets = extract_failed_targets(refresh_result)
            if (task.context_json or {}).get("data_domain") == "inventory":
                await InventoryAgeRefreshService(db).refresh(force_full=False)
            if hasattr(db, "commit"):
                await db.commit()
            if refresh_status != "success":
                error_message = (
                    f"refresh pipeline {refresh_status}: "
                    f"{', '.join(str(target) for target in failed_targets) or 'unknown target'}"
                )
                await queue_service.mark_failed(task.id, error_message)
                return {
                    "status": "failed",
                    "job_id": task.job_id,
                    "run_id": run_id,
                    "error": error_message,
                }
            await queue_service.mark_completed(task.id)
            return {"status": "success", "job_id": task.job_id, "run_id": run_id}
        except Exception as exc:  # noqa: BLE001
            if hasattr(db, "rollback"):
                await db.rollback()
            await queue_service.mark_failed(task.id, str(exc))
            logger.warning(
                "[RefreshQueue] queue task failed: job_id=%s, error=%s",
                task.job_id,
                exc,
                exc_info=True,
            )
            return {"status": "failed", "job_id": task.job_id, "error": str(exc)}
    finally:
        await db.close()


@celery_app.task(
    name="backend.tasks.refresh_queue_tasks.process_refresh_queue_task",
    bind=True,
    queue="scheduled",
    priority=5,
    time_limit=1800,
    soft_time_limit=1500,
)
def process_refresh_queue_task(self):  # noqa: ANN201
    reset_async_engine_pool_for_new_loop()
    return asyncio.run(_async_process_refresh_queue_task())
