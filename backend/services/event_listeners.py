"""Internal event listeners for ingestion and related workflows."""

from __future__ import annotations

import asyncio
from typing import Dict, Optional

from backend.models.database import (
    AsyncSessionLocal,
    SessionLocal,
    reset_async_engine_pool_for_new_loop,
)
from backend.services.cloud_b_class_auto_sync_dispatch_service import (
    CloudBClassAutoSyncDispatchService,
)
from backend.services.data_pipeline.inventory_age_refresh_service import (
    InventoryAgeRefreshService,
)
from backend.services.data_pipeline.refresh_queue_service import RefreshQueueService
from backend.services.data_pipeline.refresh_registry import (
    SQL_TARGET_PATHS,
    resolve_refresh_targets_for_source_table,
)
from backend.services.data_pipeline.refresh_runner import (
    execute_refresh_plan,
    extract_refresh_status,
    extract_run_id,
)
from backend.services.product_center_service import sync_inventory_skus
from backend.utils.events import AClassUpdatedEvent, DataIngestedEvent, MVRefreshedEvent
from modules.core.data_domains import normalize_data_domain
from modules.core.logger import get_logger

logger = get_logger(__name__)


DATA_INGESTED_REFRESH_LOCK = asyncio.Lock()


DATA_INGESTED_PIPELINE_TARGETS: Dict[str, list[str]] = {
    "orders": [
        "api.business_overview_kpi_module",
        "mart.platform_day_kpi",
        "mart.platform_week_kpi",
        "api.business_overview_comparison_platform_module",
        "api.business_overview_comparison_module",
        "api.business_overview_shop_racing_module",
        "api.business_overview_shop_racing_monthly_module",
        "api.business_overview_traffic_ranking_module",
        "api.business_overview_inventory_backlog_module",
        "api.business_overview_operational_metrics_module",
    ],
    "analytics": [
        "api.business_overview_kpi_module",
        "mart.platform_day_kpi",
        "mart.platform_week_kpi",
        "api.business_overview_comparison_platform_module",
        "api.business_overview_comparison_module",
        "api.business_overview_shop_racing_module",
        "api.business_overview_shop_racing_monthly_module",
        "api.business_overview_traffic_ranking_module",
        "api.business_overview_operational_metrics_module",
    ],
    # [D8] 原独立的 "traffic" 条目已并入 "analytics"(traffic 域自 v4.10.0 起废弃),
    #      两个 key 指向同一个业务域,保留两份会让刷新目标随时间各自漂移
    "products": [
        "api.clearance_ranking_module",
        "mart.spu_operating_current",
    ],
    "inventory": [
        "api.business_overview_inventory_backlog_module",
        "api.clearance_ranking_module",
        "mart.spu_operating_current",
    ],
    "services": [
        "semantic.fact_services_atomic",
    ],
}


def determine_pipeline_targets_for_data_ingested(event: DataIngestedEvent) -> list[str]:
    requested_targets = resolve_refresh_targets_for_source_table(
        source_table_name=event.source_table_name,
        data_domain=event.data_domain,
        granularity=event.granularity,
    )
    if not requested_targets:
        # [D8] 归一数据域(traffic -> analytics)后再取默认刷新目标
        requested_targets = list(
            DATA_INGESTED_PIPELINE_TARGETS.get(normalize_data_domain(event.data_domain), [])
        )
    registered_targets = [target for target in requested_targets if target in SQL_TARGET_PATHS]
    dropped_targets = [target for target in requested_targets if target not in SQL_TARGET_PATHS]
    if dropped_targets:
        logger.warning(
            "[EventListener] dropping unregistered refresh targets: domain=%s, file_id=%s, targets=%s",
            event.data_domain,
            event.file_id,
            dropped_targets,
        )
    return registered_targets


async def run_pipeline_refresh_for_data_ingested_event(event: DataIngestedEvent) -> Optional[str]:
    targets = determine_pipeline_targets_for_data_ingested(event)
    if not targets:
        logger.info(
            "[EventListener] DATA_INGESTED matched no PostgreSQL refresh targets: "
            f"file_id={event.file_id}, domain={event.data_domain}, granularity={event.granularity}"
        )
        return None

    async with DATA_INGESTED_REFRESH_LOCK:
        async with AsyncSessionLocal() as session:
            refresh_result = await execute_refresh_plan(
                session,
                targets=targets,
                pipeline_name="data_ingested_refresh",
                trigger_source="data_ingested_event",
                context={
                    "file_id": event.file_id,
                    "platform_code": event.platform_code,
                    "data_domain": event.data_domain,
                    "granularity": event.granularity,
                    "row_count": event.row_count,
                    "timestamp": event.timestamp,
                },
                continue_on_error=True,
                max_attempts=2,
                retry_backoff_seconds=0.1,
            )
            run_id = extract_run_id(refresh_result)
            await session.commit()
            logger.info(
                "[EventListener] PostgreSQL refresh pipeline completed: "
                f"run_id={run_id}, status={extract_refresh_status(refresh_result)}, "
                f"file_id={event.file_id}, domain={event.data_domain}, targets={len(targets)}"
            )

            if event.data_domain == "inventory":
                if hasattr(session, "execute"):
                    await sync_inventory_skus(session, source_file_id=event.file_id)
                inventory_age_result = await InventoryAgeRefreshService(session).refresh(
                    force_full=False
                )
                await session.commit()
                logger.info(
                    "[EventListener] Inventory age replay completed: "
                    f"file_id={event.file_id}, result={inventory_age_result}"
                )

            return run_id


async def enqueue_refresh_for_data_ingested_event(event: DataIngestedEvent) -> Optional[str]:
    targets = determine_pipeline_targets_for_data_ingested(event)
    if not targets:
        logger.info(
            "[EventListener] DATA_INGESTED matched no PostgreSQL refresh targets: "
            f"file_id={event.file_id}, domain={event.data_domain}, granularity={event.granularity}"
        )
        return None

    async with AsyncSessionLocal() as session:
        queue_service = RefreshQueueService(session)
        task = await queue_service.enqueue_refresh(
            trigger_type="data_ingested",
            pipeline_name="data_ingested_refresh",
            targets=targets,
            context={
                "file_id": event.file_id,
                "platform_code": event.platform_code,
                "data_domain": event.data_domain,
                "sub_domain": event.sub_domain,
                "granularity": event.granularity,
                "row_count": event.row_count,
                "source_table_name": event.source_table_name,
                "timestamp": event.timestamp,
                "related_file_ids": [event.file_id] if event.file_id is not None else [],
            },
        )
        logger.info(
            "[EventListener] PostgreSQL refresh intent enqueued: "
            f"job_id={task.job_id}, file_id={event.file_id}, domain={event.data_domain}, targets={len(targets)}"
        )
        return task.job_id


class EventListener:
    """Event listener entrypoints used by ingestion and background workflows."""

    @staticmethod
    def dispatch_service_factory():
        db = SessionLocal()
        service = CloudBClassAutoSyncDispatchService(db)
        return db, service

    @staticmethod
    async def handle_data_ingested_async(event: DataIngestedEvent) -> dict | None:
        """DATA_INGESTED 的生产入口:先把 PostgreSQL 刷新入队落库,再做同步派发。

        入队必须在这里 await 完成 —— 早先用 ``asyncio.create_task`` 把入队排进事件循环,
        而调用方跑在 Celery worker 的 ``asyncio.run(...)`` 里,收尾时会把尚未完成的 task
        取消掉。结果是刷新从未真正入队,``mart.inventory_age_current`` 一直是空的。
        """
        try:
            await enqueue_refresh_for_data_ingested_event(event)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[EventListener] DATA_INGESTED PostgreSQL refresh enqueue failed: %s",
                exc,
                exc_info=True,
            )
        return EventListener.handle_data_ingested(event, enqueue_refresh=False)

    @staticmethod
    def handle_data_ingested(
        event: DataIngestedEvent,
        *,
        enqueue_refresh: bool = True,
    ) -> dict | None:
        logger.info(
            "[EventListener] Received DATA_INGESTED event: "
            f"file_id={event.file_id}, domain={event.data_domain}, granularity={event.granularity}, "
            f"rows={event.row_count}, source_table={event.source_table_name}"
        )

        if enqueue_refresh:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                # 没有事件循环:就地跑完一次入队,保证刷新不会丢
                # [*] 必须先丢掉旧事件循环遗留的池化连接 ——
                # 否则 asyncpg 会拿着上一个 loop 的连接在新 loop 里用,
                # 直接抛 "Event loop is closed" / "'NoneType' object has no attribute 'send'"。
                # 仓库里所有「同步上下文 + asyncio.run」的入口都是这个写法。
                reset_async_engine_pool_for_new_loop()
                asyncio.run(enqueue_refresh_for_data_ingested_event(event))
            else:
                # 有事件循环时只能尽力而为:调用方若是 asyncio.run(...),
                # 收尾时未完成的 task 会被取消。生产路径请走 handle_data_ingested_async。
                task = asyncio.create_task(enqueue_refresh_for_data_ingested_event(event))
                logger.info(
                    "[EventListener] PostgreSQL refresh enqueue task scheduled: "
                    f"file_id={event.file_id}, task={task!r}"
                )

        if event.source_table_name:
            try:
                factory_result = EventListener.dispatch_service_factory()
                if isinstance(factory_result, tuple):
                    db, service = factory_result
                else:
                    db = None
                    service = factory_result
                try:
                    result = service.enqueue_or_coalesce(event)
                finally:
                    if db is not None:
                        db.close()
                logger.info(
                    "[EventListener] Cloud sync task queued: "
                    f"job_id={result['job_id']}, coalesced={result['coalesced']}"
                )
                return result
            except Exception as exc:
                logger.warning(
                    f"[EventListener] DATA_INGESTED cloud sync enqueue failed: {exc}",
                    exc_info=True,
                )
        return None

    @staticmethod
    def handle_mv_refreshed(event: MVRefreshedEvent) -> None:
        logger.info(
            "[EventListener] Received MV_REFRESHED event: "
            f"view={event.view_name}, rows={event.row_count}, duration={event.duration_seconds:.2f}s"
        )

    @staticmethod
    def handle_a_class_updated(event: AClassUpdatedEvent) -> None:
        logger.info(
            "[EventListener] Received A_CLASS_UPDATED event: "
            f"type={event.data_type}, id={event.record_id}, action={event.action}"
        )


event_listener = EventListener()
