from backend.services.cloud_b_class_auto_sync_dispatch_service import (
    CloudBClassAutoSyncDispatchService,
)
from backend.models.database import SessionLocal
from modules.core.db import CloudBClassSyncTask
from backend.utils.events import DataIngestedEvent


def _build_session():
    session = SessionLocal()
    CloudBClassSyncTask.__table__.create(bind=session.bind, checkfirst=True)
    return session


def _build_event(source_table_name: str):
    return DataIngestedEvent(
        file_id=1,
        platform_code="shopee",
        data_domain="orders",
        sub_domain=None,
        granularity="daily",
        source_table_name=source_table_name,
        row_count=10,
    )


def test_enqueue_or_coalesce_reuses_existing_pending_task():
    db = _build_session()
    table_name = "fact_shopee_orders_daily_test_reuse"
    try:
        db.query(CloudBClassSyncTask).filter(
            CloudBClassSyncTask.source_table_name == table_name
        ).delete()
        db.commit()

        service = CloudBClassAutoSyncDispatchService(db)
        first = service.enqueue_or_coalesce(_build_event(table_name))
        second = service.enqueue_or_coalesce(_build_event(table_name))

        assert first["job_id"] == second["job_id"]
        assert second["coalesced"] is True
    finally:
        db.query(CloudBClassSyncTask).filter(
            CloudBClassSyncTask.source_table_name == table_name
        ).delete()
        db.commit()
        db.close()


def test_enqueue_or_coalesce_increments_trigger_count():
    db = _build_session()
    table_name = "fact_shopee_orders_daily_test_trigger_count"
    try:
        db.query(CloudBClassSyncTask).filter(
            CloudBClassSyncTask.source_table_name == table_name
        ).delete()
        db.commit()

        service = CloudBClassAutoSyncDispatchService(db)
        service.enqueue_or_coalesce(_build_event(table_name))
        result = service.enqueue_or_coalesce(_build_event(table_name))

        assert result["metadata"]["trigger_count"] == 2
    finally:
        db.query(CloudBClassSyncTask).filter(
            CloudBClassSyncTask.source_table_name == table_name
        ).delete()
        db.commit()
        db.close()
