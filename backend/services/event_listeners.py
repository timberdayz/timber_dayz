"""Internal event listeners for ingestion and related workflows."""

from __future__ import annotations

import asyncio
from typing import Dict, Optional

from backend.models.database import AsyncSessionLocal, SessionLocal
from backend.services.cloud_b_class_auto_sync_dispatch_service import (
    CloudBClassAutoSyncDispatchService,
)
from backend.services.data_pipeline.refresh_runner import execute_refresh_plan
from backend.utils.events import AClassUpdatedEvent, DataIngestedEvent, MVRefreshedEvent
from modules.core.logger import get_logger

logger = get_logger(__name__)


DATA_INGESTED_PIPELINE_TARGETS: Dict[str, list[str]] = {
    "orders": [
        "api.business_overview_kpi_module",
        "api.business_overview_comparison_module",
        "api.business_overview_shop_racing_module",
        "api.business_overview_traffic_ranking_module",
        "api.business_overview_inventory_backlog_module",
        "api.business_overview_operational_metrics_module",
        "api.annual_summary_kpi_module",
        "api.annual_summary_trend_module",
        "api.annual_summary_platform_share_module",
        "api.annual_summary_by_shop_module",
    ],
    "analytics": [
        "api.business_overview_kpi_module",
        "api.business_overview_comparison_module",
        "api.business_overview_shop_racing_module",
        "api.business_overview_traffic_ranking_module",
        "api.business_overview_operational_metrics_module",
        "api.annual_summary_kpi_module",
        "api.annual_summary_trend_module",
        "api.annual_summary_platform_share_module",
        "api.annual_summary_by_shop_module",
    ],
    "traffic": [
        "api.business_overview_comparison_module",
        "api.business_overview_traffic_ranking_module",
        "api.business_overview_operational_metrics_module",
    ],
    "products": [
        "api.clearance_ranking_module",
    ],
    "inventory": [
        "api.business_overview_inventory_backlog_module",
        "api.clearance_ranking_module",
    ],
    "services": [
        "semantic.fact_services_atomic",
    ],
}


def determine_pipeline_targets_for_data_ingested(event: DataIngestedEvent) -> list[str]:
    return list(DATA_INGESTED_PIPELINE_TARGETS.get(event.data_domain or "", []))


async def run_pipeline_refresh_for_data_ingested_event(event: DataIngestedEvent) -> Optional[str]:
    targets = determine_pipeline_targets_for_data_ingested(event)
    if not targets:
        logger.info(
            "[EventListener] DATA_INGESTED matched no PostgreSQL refresh targets: "
            f"file_id={event.file_id}, domain={event.data_domain}, granularity={event.granularity}"
        )
        return None

    async with AsyncSessionLocal() as session:
        run_id = await execute_refresh_plan(
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
        await session.commit()
        logger.info(
            "[EventListener] PostgreSQL refresh pipeline completed: "
            f"run_id={run_id}, file_id={event.file_id}, domain={event.data_domain}, targets={len(targets)}"
        )
        return run_id


class EventListener:
    """Event listener entrypoints used by ingestion and background workflows."""

    @staticmethod
    def handle_data_ingested(event: DataIngestedEvent) -> None:
        logger.info(
            "[EventListener] Received DATA_INGESTED event: "
            f"file_id={event.file_id}, domain={event.data_domain}, granularity={event.granularity}, "
            f"rows={event.row_count}, source_table={event.source_table_name}"
        )

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            try:
                run_id = asyncio.run(run_pipeline_refresh_for_data_ingested_event(event))
                logger.info(
                    "[EventListener] Synchronous PostgreSQL refresh completed: "
                    f"file_id={event.file_id}, run_id={run_id}"
                )
            except Exception as exc:
                logger.warning(
                    f"[EventListener] DATA_INGESTED synchronous PostgreSQL refresh failed: {exc}",
                    exc_info=True,
                )
        else:
            task = asyncio.create_task(run_pipeline_refresh_for_data_ingested_event(event))
            logger.info(
                "[EventListener] PostgreSQL refresh background task scheduled: "
                f"file_id={event.file_id}, task={task!r}"
            )

        if event.source_table_name:
            try:
                db = SessionLocal()
                try:
                    service = CloudBClassAutoSyncDispatchService(db)
                    result = service.enqueue_or_coalesce(event)
                finally:
                    db.close()
                logger.info(
                    "[EventListener] Cloud sync task queued: "
                    f"job_id={result['job_id']}, coalesced={result['coalesced']}"
                )
            except Exception as exc:
                logger.warning(
                    f"[EventListener] DATA_INGESTED cloud sync enqueue failed: {exc}",
                    exc_info=True,
                )

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
