import asyncio
from datetime import datetime, timedelta, timezone

from backend.models.database import SessionLocal
from backend.services.cloud_b_class_auto_sync_worker import CloudBClassAutoSyncWorker
from modules.core.db import CloudBClassSyncTask


class FakeSyncExecutor:
    def __init__(self, should_fail: bool = False, error_code: str | None = None, sync_ok: bool = True, projection_ok: bool = True):
        self.should_fail = should_fail
        self.error_code = error_code
        self.sync_ok = sync_ok
        self.projection_ok = projection_ok

    def sync_table(self, source_table_name: str):
        if self.should_fail:
            raise RuntimeError(self.error_code or "sync_failed")
        return {
            "status": "completed" if self.sync_ok else "failed",
            "projection_status": "completed" if self.projection_ok else "failed",
            "source_table_name": source_table_name,
        }


def _build_session():
    session = SessionLocal()
    CloudBClassSyncTask.__table__.create(bind=session.bind, checkfirst=True)
    return session


def _create_task(db, source_table_name: str = "fact_shopee_orders_daily", status: str = "pending"):
    task = CloudBClassSyncTask(
        job_id=f"job-{source_table_name}-{status}",
        dedupe_key=source_table_name,
        source_table_name=source_table_name,
        platform_code="shopee",
        data_domain="orders",
        granularity="daily",
        status=status,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def test_worker_claims_one_runnable_task():
    db = _build_session()
    try:
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        _create_task(db)

        worker = CloudBClassAutoSyncWorker(db, sync_executor=FakeSyncExecutor())
        task = worker.claim_next_task(worker_id="worker-1")

        assert task is not None
        assert task.claimed_by == "worker-1"
        assert task.status == "running"
    finally:
        db.rollback()
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        db.close()


def test_worker_moves_retryable_failure_to_retry_waiting():
    db = _build_session()
    try:
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        pending_task = _create_task(db)

        executor = FakeSyncExecutor(should_fail=True, error_code="cloud_db_unavailable")
        worker = CloudBClassAutoSyncWorker(db, sync_executor=executor)
        asyncio.run(worker.run_one(worker_id="worker-1"))
        refreshed = db.get(type(pending_task), pending_task.id)

        assert refreshed.status == "retry_waiting"
        assert refreshed.error_code == "cloud_db_unavailable"
        assert refreshed.next_retry_at is not None
    finally:
        db.rollback()
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        db.close()


def test_worker_marks_partial_success_when_projection_fails():
    db = _build_session()
    try:
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        pending_task = _create_task(db)

        executor = FakeSyncExecutor(sync_ok=True, projection_ok=False)
        worker = CloudBClassAutoSyncWorker(db, sync_executor=executor)
        asyncio.run(worker.run_one(worker_id="worker-1"))
        refreshed = db.get(type(pending_task), pending_task.id)

        assert refreshed.status == "partial_success"
        assert refreshed.projection_status == "failed"
    finally:
        db.rollback()
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        db.close()


def test_stale_lease_can_be_reclaimed():
    db = _build_session()
    try:
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        task = _create_task(db, status="running")
        task.claimed_by = "worker-old"
        task.lease_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()

        worker = CloudBClassAutoSyncWorker(db, sync_executor=FakeSyncExecutor())
        claimed = worker.claim_next_task(worker_id="worker-new")

        assert claimed is not None
        assert claimed.claimed_by == "worker-new"
    finally:
        db.rollback()
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        db.close()


def test_worker_supports_async_sync_executor():
    db = _build_session()
    try:
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        pending_task = _create_task(db, source_table_name="fact_shopee_orders_daily_async")

        class AsyncExecutor:
            async def sync_table(self, source_table_name: str):
                return {
                    "status": "completed",
                    "projection_status": "completed",
                    "source_table_name": source_table_name,
                }

        worker = CloudBClassAutoSyncWorker(db, sync_executor=AsyncExecutor())
        asyncio.run(worker.run_one(worker_id="worker-1"))
        refreshed = db.get(type(pending_task), pending_task.id)

        assert refreshed.status == "completed"
    finally:
        db.rollback()
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        db.close()
