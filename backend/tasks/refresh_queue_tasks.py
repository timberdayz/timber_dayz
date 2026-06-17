from __future__ import annotations

import asyncio

from backend.celery_app import celery_app
from backend.models.database import AsyncSessionLocal, reset_async_engine_pool_for_new_loop
from backend.services.data_pipeline.inventory_age_refresh_service import InventoryAgeRefreshService
from backend.services.cache_service import get_cache_service
from backend.services.data_pipeline.dashboard_bootstrap import (
    DASHBOARD_MODULE_TARGETS,
    bootstrap_dashboard_assets_if_needed,
    inspect_dashboard_assets,
)
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


def _modules_for_targets(targets: list[str]) -> list[str]:
    matched: list[str] = []
    target_set = set(targets)
    for module_name, module_targets in DASHBOARD_MODULE_TARGETS.items():
        module_target_set = set(module_targets.get("core_targets", [])) | set(
            module_targets.get("refresh_targets", [])
        )
        if target_set & module_target_set:
            matched.append(module_name)
    return matched


async def _repair_dashboard_assets_if_needed(db, targets: list[str]) -> None:
    modules = _modules_for_targets(targets)
    if not modules:
        return
    try:
        report = await inspect_dashboard_assets(db)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[RefreshQueue] dashboard asset readiness inspection skipped before refresh: %s",
            exc,
            exc_info=True,
        )
        return
    module_reports = report.get("modules") if isinstance(report, dict) else None
    if not isinstance(module_reports, dict):
        return
    for module_name in modules:
        module_report = module_reports.get(module_name)
        if not isinstance(module_report, dict):
            continue
        if module_report.get("status") != "drift":
            continue
        try:
            await bootstrap_dashboard_assets_if_needed(
                db,
                wait_for_lock=True,
                module=module_name,
            )
            if hasattr(db, "commit"):
                await db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[RefreshQueue] dashboard asset repair failed before refresh: module=%s error=%s",
                module_name,
                exc,
                exc_info=True,
            )


async def _invalidate_refresh_target_caches(targets: list[str]) -> None:
    modules = set(_modules_for_targets(targets))
    if not modules:
        return
    try:
        cache_service = get_cache_service()
        if "business_overview" in modules:
            await cache_service.invalidate_dashboard_business_overview()
        if "clearance_ranking" in modules:
            await cache_service.invalidate("dashboard_clearance_ranking")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[RefreshQueue] cache invalidation failed after refresh: %s",
            exc,
            exc_info=True,
        )


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
            targets = list(task.targets_json or [])
            await _repair_dashboard_assets_if_needed(db, targets)
            refresh_result = await execute_refresh_plan(
                db,
                targets=targets,
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
            await _invalidate_refresh_target_caches(targets)
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
