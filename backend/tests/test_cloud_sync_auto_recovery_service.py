from datetime import datetime, timedelta, timezone

import pytest

from backend.services.cloud_sync_auto_recovery_service import (
    CLOUD_SYNC_RECOVERABLE_ERROR_CODES,
    CloudSyncAutoRecoveryService,
)


class _FakeTask:
    def __init__(
        self,
        *,
        task_id: int,
        status: str,
        error_code: str | None = None,
        lease_expires_at=None,
        attempt_count: int = 1,
        metadata_json=None,
    ):
        self.id = task_id
        self.job_id = f"job-{task_id}"
        self.status = status
        self.error_code = error_code
        self.lease_expires_at = lease_expires_at
        self.attempt_count = attempt_count
        self.claimed_by = "worker-1"
        self.heartbeat_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        self.last_error = "previous error"
        self.finished_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        self.next_retry_at = None
        self.metadata_json = metadata_json or {}


class _FakeCatalogFile:
    def __init__(
        self,
        *,
        file_id: int,
        status: str = "pending",
        first_seen_at=None,
        file_metadata=None,
    ):
        self.id = file_id
        self.status = status
        self.first_seen_at = first_seen_at or datetime.now(timezone.utc) - timedelta(minutes=15)
        self.file_metadata = file_metadata or {}


class _FakeScalarResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _FakeSession:
    def __init__(self, tasks):
        self.tasks = tasks
        self.committed = False

    def execute(self, stmt):
        return _FakeScalarResult(self.tasks)

    def commit(self):
        self.committed = True

    def rollback(self):
        return None


def test_cloud_sync_auto_recovery_requeues_recoverable_failed_tasks():
    task = _FakeTask(
        task_id=175,
        status="failed",
        error_code="legacy_scope_stale_recovered",
        attempt_count=20,
    )
    session = _FakeSession([task])
    service = CloudSyncAutoRecoveryService(session)

    result = service.recover_cloud_sync_tasks(limit=10)

    assert result["recovered"] == 1
    assert task.status == "pending"
    assert task.claimed_by is None
    assert task.lease_expires_at is None
    assert task.heartbeat_at is None
    assert task.last_error is None
    assert task.error_code is None
    assert task.finished_at is None
    assert task.metadata_json["auto_recovery"]["previous_status"] == "failed"
    assert task.metadata_json["auto_recovery"]["previous_error_code"] == "legacy_scope_stale_recovered"
    assert task.metadata_json["auto_recovery"]["attempt_override"] is True
    assert session.committed is True


def test_cloud_sync_auto_recovery_skips_non_recoverable_failed_tasks():
    task = _FakeTask(
        task_id=201,
        status="failed",
        error_code="schema_incompatible",
    )
    session = _FakeSession([task])
    service = CloudSyncAutoRecoveryService(session)

    result = service.recover_cloud_sync_tasks(limit=10)

    assert result["recovered"] == 0
    assert task.status == "failed"
    assert session.committed is False


def test_cloud_sync_auto_recovery_requeues_stale_running_tasks():
    task = _FakeTask(
        task_id=202,
        status="running",
        lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        error_code=None,
    )
    session = _FakeSession([task])
    service = CloudSyncAutoRecoveryService(session)

    result = service.recover_cloud_sync_tasks(limit=10)

    assert result["recovered"] == 1
    assert task.status == "pending"
    assert task.error_code is None
    assert task.metadata_json["auto_recovery"]["recovery_reason"] == "task_stale_running"


def test_cloud_sync_auto_recovery_error_code_whitelist_is_explicit():
    assert {
        "legacy_scope_stale_recovered",
        "cloud_receive_log_missing",
        "cloud_receive_log_table_missing_after_migration",
        "cloud_db_transient_unavailable",
        "worker_lost",
        "lease_expired",
        "task_stale_running",
    }.issubset(CLOUD_SYNC_RECOVERABLE_ERROR_CODES)


def test_cloud_sync_auto_recovery_enqueues_overdue_pending_catalog_files(monkeypatch):
    overdue = _FakeCatalogFile(file_id=2803)
    fresh = _FakeCatalogFile(file_id=2804, first_seen_at=datetime.now(timezone.utc))
    session = _FakeSession([overdue, fresh])
    enqueued = []

    class _FakeTaskHandle:
        id = "celery-2803"

    def fake_apply_async(*, kwargs, queue=None):
        enqueued.append({"kwargs": kwargs, "queue": queue})
        return _FakeTaskHandle()

    monkeypatch.setattr(
        "backend.tasks.data_sync_tasks.sync_single_file_task.apply_async",
        fake_apply_async,
    )
    service = CloudSyncAutoRecoveryService(session)

    result = service.enqueue_overdue_pending_catalog_files(limit=10, overdue_minutes=10)

    assert result["enqueued"] == 1
    assert result["file_ids"] == [2803]
    assert enqueued == [{"kwargs": {"file_id": 2803}, "queue": "data_sync"}]
    assert overdue.file_metadata["auto_ingest"]["current_task_id"] == "celery-2803"
    assert overdue.file_metadata["auto_ingest"]["recovered_by"] == "auto_recovery"
    assert session.committed is True


def test_cloud_sync_auto_recovery_does_not_enqueue_template_update_required_files(monkeypatch):
    template_required = _FakeCatalogFile(file_id=2800, status="template_update_required")
    session = _FakeSession([template_required])

    def fail_apply_async(**kwargs):
        raise AssertionError("template_update_required files must not be auto-enqueued")

    monkeypatch.setattr(
        "backend.tasks.data_sync_tasks.sync_single_file_task.apply_async",
        fail_apply_async,
    )
    service = CloudSyncAutoRecoveryService(session)

    result = service.enqueue_overdue_pending_catalog_files(limit=10, overdue_minutes=10)

    assert result["enqueued"] == 0
    assert session.committed is False


def test_cloud_sync_auto_recovery_run_once_includes_pending_catalog_file_recovery(monkeypatch):
    overdue = _FakeCatalogFile(file_id=2805)
    session = _FakeSession([overdue])

    class _FakeTaskHandle:
        id = "celery-2805"

    monkeypatch.setattr(
        "backend.tasks.data_sync_tasks.sync_single_file_task.apply_async",
        lambda *, kwargs, queue=None: _FakeTaskHandle(),
    )
    service = CloudSyncAutoRecoveryService(session)

    result = service.run_once(limit=10)

    assert result["pending_catalog_files"]["enqueued"] == 1
    assert result["pending_catalog_files"]["file_ids"] == [2805]
