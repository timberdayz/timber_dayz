import asyncio
import os
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.services.cloud_b_class_auto_sync_worker import CloudBClassAutoSyncWorker
from modules.core.db import CloudBClassSyncTask, SystemConfig, TaskCenterTask


class FakeSyncExecutor:
    def __init__(self, should_fail: bool = False, error_code: str | None = None, sync_ok: bool = True, projection_ok: bool = True):
        self.should_fail = should_fail
        self.error_code = error_code
        self.sync_ok = sync_ok
        self.projection_ok = projection_ok
        self.batch_sizes = []

    def sync_table(self, source_table_name: str, batch_size: int = 1000):
        self.batch_sizes.append(batch_size)
        if self.should_fail:
            raise RuntimeError(self.error_code or "sync_failed")
        return {
            "status": "completed" if self.sync_ok else "failed",
            "projection_status": "completed" if self.projection_ok else "failed",
            "source_table_name": source_table_name,
        }


def _build_session():
    os.environ["CLOUD_SYNC_AUTO_SYNC_ENABLED"] = "true"
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    CloudBClassSyncTask.__table__.create(bind=engine, checkfirst=True)
    SystemConfig.__table__.create(bind=engine, checkfirst=True)
    TaskCenterTask.__table__.create(bind=engine, checkfirst=True)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _as_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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


def test_worker_marks_completed_when_projection_refresh_is_queued():
    db = _build_session()
    try:
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        pending_task = _create_task(db)

        class QueuedProjectionExecutor:
            def sync_table(self, source_table_name: str, batch_size: int = 1000):
                return {
                    "status": "completed",
                    "projection_status": "queued",
                    "refresh_queue_job_id": "refresh-job-1",
                    "source_table_name": source_table_name,
                }

        worker = CloudBClassAutoSyncWorker(db, sync_executor=QueuedProjectionExecutor())
        asyncio.run(worker.run_one(worker_id="worker-1"))
        refreshed = db.get(type(pending_task), pending_task.id)

        assert refreshed.status == "completed"
        assert refreshed.projection_status == "queued"
        assert refreshed.last_error is None
        assert refreshed.error_code is None
    finally:
        db.rollback()
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        db.close()


def test_worker_marks_failed_when_sync_executor_returns_failed_status():
    db = _build_session()
    try:
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        pending_task = _create_task(db)

        executor = FakeSyncExecutor(sync_ok=False, projection_ok=True)
        worker = CloudBClassAutoSyncWorker(db, sync_executor=executor)
        asyncio.run(worker.run_one(worker_id="worker-1"))
        refreshed = db.get(type(pending_task), pending_task.id)

        assert refreshed.status == "failed"
        assert refreshed.next_retry_at is None
    finally:
        db.rollback()
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        db.close()


def test_worker_stores_long_sync_failure_with_short_error_code():
    db = _build_session()
    try:
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        pending_task = _create_task(db)
        long_error = (
            '(psycopg2.OperationalError) connection to server at "127.0.0.1", '
            "port 15433 failed: server closed the connection unexpectedly\n"
            "This probably means the server terminated abnormally before or while "
            "processing the request."
        )

        class FailingExecutor:
            def sync_table(self, source_table_name: str, batch_size: int = 1000):
                return {
                    "status": "failed",
                    "error": long_error,
                }

        worker = CloudBClassAutoSyncWorker(db, sync_executor=FailingExecutor())
        asyncio.run(worker.run_one(worker_id="worker-1"))
        refreshed = db.get(type(pending_task), pending_task.id)

        assert refreshed.status == "retry_waiting"
        assert refreshed.last_error == long_error
        assert refreshed.error_code == "cloud_db_connection_closed"
        assert len(refreshed.error_code) <= 64
        assert refreshed.next_retry_at is not None
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
            async def sync_table(self, source_table_name: str, batch_size: int = 1000):
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


def test_worker_sets_finished_at_after_successful_run():
    db = _build_session()
    try:
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        pending_task = _create_task(db, source_table_name="fact_shopee_orders_daily_finished_at")

        worker = CloudBClassAutoSyncWorker(db, sync_executor=FakeSyncExecutor())
        asyncio.run(worker.run_one(worker_id="worker-1"))
        refreshed = db.get(type(pending_task), pending_task.id)

        assert refreshed.status == "completed"
        assert refreshed.finished_at is not None
    finally:
        db.rollback()
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        db.close()


def test_worker_heartbeat_extends_lease():
    db = _build_session()
    try:
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        task = _create_task(db)

        worker = CloudBClassAutoSyncWorker(db, sync_executor=FakeSyncExecutor(), lease_seconds=300)
        claimed = worker.claim_next_task(worker_id="worker-1")
        original_lease = claimed.lease_expires_at

        worker.heartbeat(claimed.id, worker_id="worker-1")
        refreshed = db.get(type(task), task.id)

        assert refreshed.heartbeat_at is not None
        assert _as_utc(refreshed.lease_expires_at) >= _as_utc(original_lease)
    finally:
        db.rollback()
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        db.close()


def test_worker_renews_lease_while_async_sync_is_running():
    db = _build_session()
    try:
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        pending_task = _create_task(db, source_table_name="fact_shopee_orders_daily_long_run")

        class SlowAsyncExecutor:
            async def sync_table(self, source_table_name: str, batch_size: int = 1000):
                await asyncio.sleep(0.12)
                return {
                    "status": "completed",
                    "projection_status": "completed",
                    "source_table_name": source_table_name,
                }

        worker = CloudBClassAutoSyncWorker(db, sync_executor=SlowAsyncExecutor(), lease_seconds=0.05)
        asyncio.run(worker.run_one(worker_id="worker-1"))
        refreshed = db.get(type(pending_task), pending_task.id)

        assert refreshed.status == "completed"
        assert refreshed.heartbeat_at is not None
        assert refreshed.heartbeat_at > refreshed.last_attempt_started_at
    finally:
        db.rollback()
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        db.close()


def test_worker_renews_lease_while_blocking_sync_is_running():
    db = _build_session()
    try:
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        pending_task = _create_task(db, source_table_name="fact_shopee_orders_daily_blocking")
        observed = {}

        class BlockingExecutor:
            def sync_table(self, source_table_name: str, batch_size: int = 1000):
                time.sleep(0.12)
                return {
                    "status": "completed",
                    "projection_status": "completed",
                    "source_table_name": source_table_name,
                }

        worker = CloudBClassAutoSyncWorker(db, sync_executor=BlockingExecutor(), lease_seconds=0.05)

        def _run():
            asyncio.run(worker.run_one(worker_id="worker-1"))

        thread = threading.Thread(target=_run)
        thread.start()
        time.sleep(0.09)
        observed_task = db.get(type(pending_task), pending_task.id)
        observed["mid_heartbeat"] = observed_task.heartbeat_at
        observed["mid_lease"] = observed_task.lease_expires_at
        thread.join(timeout=2)
        refreshed = db.get(type(pending_task), pending_task.id)

        assert refreshed.status == "completed"
        assert observed["mid_heartbeat"] is not None
        assert _as_utc(observed["mid_heartbeat"]) > _as_utc(refreshed.last_attempt_started_at)
        assert observed["mid_lease"] is not None
        assert refreshed.heartbeat_at is not None
    finally:
        db.rollback()
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        db.close()


def test_worker_marks_retryable_failure_as_failed_after_retry_limit():
    db = _build_session()
    try:
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        pending_task = _create_task(db)
        pending_task.attempt_count = 4
        db.commit()

        executor = FakeSyncExecutor(should_fail=True, error_code="cloud_db_unavailable")
        worker = CloudBClassAutoSyncWorker(db, sync_executor=executor)
        asyncio.run(worker.run_one(worker_id="worker-1"))
        refreshed = db.get(type(pending_task), pending_task.id)

        assert refreshed.status == "failed"
        assert refreshed.next_retry_at is None
    finally:
        db.rollback()
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        db.close()


def test_worker_does_not_claim_retry_waiting_task_before_next_retry_at():
    db = _build_session()
    try:
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        task = _create_task(db, status="retry_waiting")
        task.next_retry_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        db.commit()

        worker = CloudBClassAutoSyncWorker(db, sync_executor=FakeSyncExecutor())
        claimed = worker.claim_next_task(worker_id="worker-1")

        assert claimed is None
    finally:
        db.rollback()
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        db.close()


def test_worker_claims_retry_waiting_task_after_next_retry_at():
    db = _build_session()
    try:
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        task = _create_task(db, status="retry_waiting")
        task.next_retry_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()

        worker = CloudBClassAutoSyncWorker(db, sync_executor=FakeSyncExecutor())
        claimed = worker.claim_next_task(worker_id="worker-1")

        assert claimed is not None
        assert claimed.id == task.id
        assert claimed.status == "running"
    finally:
        db.rollback()
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        db.close()


def test_worker_does_not_claim_task_when_auto_sync_is_paused(monkeypatch):
    db = _build_session()
    try:
        monkeypatch.setenv("CLOUD_SYNC_AUTO_SYNC_ENABLED", "false")
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        _create_task(db)

        worker = CloudBClassAutoSyncWorker(db, sync_executor=FakeSyncExecutor())
        claimed = worker.claim_next_task(worker_id="worker-1")

        assert claimed is None
    finally:
        db.rollback()
        db.query(CloudBClassSyncTask).delete()
        db.commit()
        db.close()
