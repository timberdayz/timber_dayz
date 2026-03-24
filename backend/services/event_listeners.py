"""Internal event listeners for ingestion and related workflows."""

from __future__ import annotations

from modules.core.logger import get_logger
from backend.utils.events import DataIngestedEvent, MVRefreshedEvent, AClassUpdatedEvent

logger = get_logger(__name__)


class EventListener:
    """Event listener entrypoints used by ingestion and background workflows."""

    dispatch_service_factory = None

    @staticmethod
    def handle_data_ingested(event: DataIngestedEvent) -> dict:
        if not event.source_table_name:
            raise ValueError("DataIngestedEvent.source_table_name is required")

        logger.info(
            "[EventListener] Received DATA_INGESTED event for cloud sync enqueue: "
            f"file_id={event.file_id}, domain={event.data_domain}, "
            f"granularity={event.granularity}, rows={event.row_count}, "
            f"source_table={event.source_table_name}"
        )

        service = EventListener._build_dispatch_service()
        result = service.enqueue_or_coalesce(event)

        logger.info(
            "[EventListener] Cloud sync task queued: "
            f"job_id={result['job_id']}, coalesced={result['coalesced']}"
        )
        return result

    @staticmethod
    def handle_mv_refreshed(event: MVRefreshedEvent) -> None:
        logger.info(
            "[EventListener] Received MV_REFRESHED event: "
            f"view={event.view_name}, rows={event.row_count}, "
            f"duration={event.duration_seconds:.2f}s"
        )

    @staticmethod
    def handle_a_class_updated(event: AClassUpdatedEvent) -> None:
        logger.info(
            "[EventListener] Received A_CLASS_UPDATED event: "
            f"type={event.data_type}, id={event.record_id}, action={event.action}"
        )

    @staticmethod
    def _build_dispatch_service():
        if EventListener.dispatch_service_factory is not None:
            return EventListener.dispatch_service_factory()

        from backend.models.database import SessionLocal
        from backend.services.cloud_b_class_auto_sync_dispatch_service import (
            CloudBClassAutoSyncDispatchService,
        )

        db = SessionLocal()

        class _Wrapper:
            def __init__(self, db_session):
                self._db_session = db_session
                self._service = CloudBClassAutoSyncDispatchService(db_session)

            def enqueue_or_coalesce(self, event):
                try:
                    return self._service.enqueue_or_coalesce(event)
                finally:
                    self._db_session.close()

        return _Wrapper(db)


event_listener = EventListener()
