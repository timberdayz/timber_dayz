import asyncio
from types import SimpleNamespace


def test_reset_async_engine_pool_for_new_loop_disposes_engine(monkeypatch):
    from backend.models import database as database_module

    called = {"dispose": 0}

    class _FakeSyncEngine:
        def dispose(self, close=False):
            called["dispose"] += 1
            called["close"] = close

    class _FakeAsyncEngine:
        sync_engine = _FakeSyncEngine()

    monkeypatch.setattr(database_module, "async_engine", _FakeAsyncEngine(), raising=False)

    database_module.reset_async_engine_pool_for_new_loop()

    assert called["dispose"] == 1
    assert called["close"] is False


def test_auto_ingest_pending_files_resets_async_engine_before_asyncio_run(monkeypatch):
    from backend.tasks import scheduled_tasks as scheduled_module

    calls = []

    class _FakeScalarResult:
        def scalars(self):
            return self

        def all(self):
            return [101]

    class _FakeSession:
        def execute(self, _stmt):
            return _FakeScalarResult()

        def close(self):
            return None

    monkeypatch.setattr(scheduled_module, "SessionLocal", lambda: _FakeSession(), raising=False)
    monkeypatch.setattr(
        scheduled_module,
        "reset_async_engine_pool_for_new_loop",
        lambda: calls.append("reset"),
        raising=False,
    )
    monkeypatch.setattr(
        scheduled_module.asyncio,
        "run",
        lambda coro: (calls.append("run"), coro.close(), [{"status": "skipped", "message": "no_template"}])[2],
    )

    result = scheduled_module.auto_ingest_pending_files(max_files=1)

    assert result["status"] == "success"
    assert calls[:2] == ["reset", "run"]


def test_auto_ingest_pending_files_creates_auto_ingest_task_record(monkeypatch):
    from backend.tasks import scheduled_tasks as scheduled_module

    records = {"links": []}

    class _FakeScalarResult:
        def scalars(self):
            return self

        def all(self):
            return [101, 102, 103]

    class _FakeSession:
        def execute(self, _stmt):
            return _FakeScalarResult()

        def close(self):
            return None

    class _FakeTaskCenterSyncService:
        def __init__(self, db):
            self.db = db

        def create_task(self, **fields):
            records["created"] = fields
            return SimpleNamespace(task_id=fields["task_id"])

        def get_task(self, task_id):
            return SimpleNamespace(task_id=task_id)

        def update_task(self, task, **updates):
            records["updated"] = updates
            return task

        def add_link(self, task_id, *, subject_type, subject_id=None, subject_key=None, details_json=None):
            records["links"].append(
                {
                    "task_id": task_id,
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "subject_key": subject_key,
                    "details_json": details_json,
                }
            )

    results = [
        {"status": "success", "file_id": 101, "file_name": "ok.xlsx"},
        {"success": False, "file_id": 102, "file_name": "bad.xlsx", "message": "boom"},
        {
            "status": "skipped",
            "file_id": 103,
            "file_name": "skip.xlsx",
            "error_code": "NO_TEMPLATE",
            "message": "template missing",
        },
    ]

    monkeypatch.setattr(scheduled_module, "SessionLocal", lambda: _FakeSession(), raising=False)
    monkeypatch.setattr(
        scheduled_module,
        "reset_async_engine_pool_for_new_loop",
        lambda: None,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.services.task_center_sync_service.TaskCenterSyncService",
        _FakeTaskCenterSyncService,
    )
    monkeypatch.setattr(
        scheduled_module.asyncio,
        "run",
        lambda coro: (coro.close(), results)[1],
    )

    result = scheduled_module.auto_ingest_pending_files(max_files=3)

    assert result["status"] == "success"
    assert records["created"]["task_family"] == "data_sync"
    assert records["created"]["task_type"] == "auto_ingest"
    assert records["created"]["trigger_source"] == "auto_ingest"
    assert records["created"]["status"] == "running"
    assert records["created"]["total_items"] == 3
    assert len(records["links"]) == 3
    assert {link["subject_id"] for link in records["links"]} == {"101", "102", "103"}

    updated = records["updated"]
    assert updated["status"] == "partial_success"
    assert updated["processed_items"] == 3
    assert updated["success_items"] == 1
    assert updated["failed_items"] == 1
    assert updated["skipped_items"] == 1
    assert updated["progress_percent"] == 100.0

    task_details = updated["details_json"]["task_details"]
    assert task_details["success_files"] == 1
    assert task_details["failed_files"] == 1
    assert task_details["skipped_files"] == 1
    assert task_details["skipped_no_template"] == 1
    assert task_details["files"] == [
        {"file_id": 101, "file_name": "ok.xlsx", "status": "success", "error_code": None, "message": ""},
        {"file_id": 102, "file_name": "bad.xlsx", "status": "failed", "error_code": None, "message": "boom"},
        {
            "file_id": 103,
            "file_name": "skip.xlsx",
            "status": "skipped",
            "error_code": "NO_TEMPLATE",
            "message": "template missing",
        },
    ]


def test_auto_ingest_pending_files_records_quarantined_success_result(monkeypatch):
    from backend.tasks import scheduled_tasks as scheduled_module

    records = {}

    class _FakeScalarResult:
        def scalars(self):
            return self

        def all(self):
            return [201]

    class _FakeSession:
        def execute(self, _stmt):
            return _FakeScalarResult()

        def close(self):
            return None

    class _FakeTaskCenterSyncService:
        def __init__(self, db):
            self.db = db

        def create_task(self, **fields):
            records["created"] = fields
            return SimpleNamespace(task_id=fields["task_id"])

        def get_task(self, task_id):
            return SimpleNamespace(task_id=task_id)

        def update_task(self, task, **updates):
            records["updated"] = updates
            return task

        def add_link(self, *args, **kwargs):
            return None

    results = [
        {
            "success": True,
            "status": "success",
            "file_id": 201,
            "file_name": "partial.xlsx",
            "quarantined": 2,
            "message": "partial rows quarantined",
        }
    ]

    monkeypatch.setattr(scheduled_module, "SessionLocal", lambda: _FakeSession(), raising=False)
    monkeypatch.setattr(
        scheduled_module,
        "reset_async_engine_pool_for_new_loop",
        lambda: None,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.services.task_center_sync_service.TaskCenterSyncService",
        _FakeTaskCenterSyncService,
    )
    monkeypatch.setattr(
        scheduled_module.asyncio,
        "run",
        lambda coro: (coro.close(), results)[1],
    )

    result = scheduled_module.auto_ingest_pending_files(max_files=1)

    assert result["status"] == "success"
    assert result["summary"]["succeeded"] == 0
    assert result["summary"]["quarantined"] == 1
    assert records["updated"]["status"] == "completed"
    task_details = records["updated"]["details_json"]["task_details"]
    assert task_details["quarantined_files"] == 1
    assert task_details["files"][0]["status"] == "quarantined"


def test_auto_ingest_pending_files_does_not_create_task_when_no_pending_files(monkeypatch):
    from backend.tasks import scheduled_tasks as scheduled_module

    class _FakeScalarResult:
        def scalars(self):
            return self

        def all(self):
            return []

    class _FakeSession:
        def execute(self, _stmt):
            return _FakeScalarResult()

        def close(self):
            return None

    class _UnexpectedTaskCenterSyncService:
        def __init__(self, _db):
            raise AssertionError("empty auto-ingest runs should not create task records")

    monkeypatch.setattr(scheduled_module, "SessionLocal", lambda: _FakeSession(), raising=False)
    monkeypatch.setattr(
        "backend.services.task_center_sync_service.TaskCenterSyncService",
        _UnexpectedTaskCenterSyncService,
    )

    result = scheduled_module.auto_ingest_pending_files(max_files=3)

    assert result == {"status": "success", "processed": 0, "details": []}


def test_sync_single_file_task_resets_async_engine_before_asyncio_run(monkeypatch):
    from backend.tasks import data_sync_tasks as task_module

    calls = []

    monkeypatch.setattr(
        task_module,
        "reset_async_engine_pool_for_new_loop",
        lambda: calls.append("reset"),
        raising=False,
    )
    monkeypatch.setattr(
        task_module.asyncio,
        "run",
        lambda coro: (calls.append("run"), coro.close(), {"success": True})[2],
    )

    result = task_module.sync_single_file_task.run(file_id=1, task_id="task-1")

    assert result["success"] is True
    assert calls[:2] == ["reset", "run"]


def test_auto_ingest_pending_files_skips_template_update_required(monkeypatch):
    from backend.tasks import scheduled_tasks as scheduled_module
    original_asyncio_run = asyncio.run
    records = {}

    class _FakeScalarResult:
        def scalars(self):
            return self

        def all(self):
            return [101]

    class _FakeSession:
        def execute(self, _stmt):
            return _FakeScalarResult()

        def close(self):
            return None

    class _FakeAsyncSession:
        async def rollback(self):
            return None

        async def close(self):
            return None

    class _FakeTaskCenterSyncService:
        def __init__(self, db):
            self.db = db

        def create_task(self, **fields):
            records["created"] = fields
            return SimpleNamespace(task_id=fields["task_id"])

        def get_task(self, task_id):
            return SimpleNamespace(task_id=task_id)

        def update_task(self, task, **updates):
            records["updated"] = updates
            return task

        def add_link(self, *args, **kwargs):
            return None

    class _FakeDataSyncService:
        def __init__(self, db):
            self.db = db

        async def get_file_sync_readiness(self, file_id, use_template_header_row=True):
            return {
                "ready": False,
                "file_id": file_id,
                "file_name": "sample.xlsx",
                "template_status": "update_required",
                "should_auto_sync": False,
                "update_reason": "新增3个字段, 删除2个字段 (匹配率: 61.5%)",
            }

        async def sync_single_file(self, *args, **kwargs):
            raise AssertionError("sync_single_file should not run when template update is required")

    monkeypatch.setattr(scheduled_module, "SessionLocal", lambda: _FakeSession(), raising=False)
    monkeypatch.setattr(
        scheduled_module,
        "reset_async_engine_pool_for_new_loop",
        lambda: None,
        raising=False,
    )
    monkeypatch.setattr("backend.services.data_sync_service.DataSyncService", _FakeDataSyncService)
    monkeypatch.setattr("backend.models.database.AsyncSessionLocal", lambda: _FakeAsyncSession())
    monkeypatch.setattr(
        "backend.services.task_center_sync_service.TaskCenterSyncService",
        _FakeTaskCenterSyncService,
    )

    def _fake_async_run(coro):
        return original_asyncio_run(coro)

    monkeypatch.setattr(scheduled_module.asyncio, "run", _fake_async_run)

    result = scheduled_module.auto_ingest_pending_files(max_files=1)

    assert result["status"] == "success"
    assert result["summary"]["skipped"] == 1
    assert result["summary"]["skipped_template_update"] == 1
    task_details = records["updated"]["details_json"]["task_details"]
    assert task_details["skipped_template_update"] == 1
    assert task_details["files"][0]["error_code"] == "TEMPLATE_UPDATE_REQUIRED"


def test_auto_ingest_pending_files_marks_task_failed_on_top_level_exception(monkeypatch):
    from backend.tasks import scheduled_tasks as scheduled_module

    records = {}

    class _FakeScalarResult:
        def scalars(self):
            return self

        def all(self):
            return [101]

    class _FakeSession:
        def execute(self, _stmt):
            return _FakeScalarResult()

        def close(self):
            return None

    class _FakeTaskCenterSyncService:
        def __init__(self, db):
            self.db = db

        def create_task(self, **fields):
            records["created"] = fields
            return SimpleNamespace(task_id=fields["task_id"])

        def get_task(self, task_id):
            return SimpleNamespace(task_id=task_id)

        def update_task(self, task, **updates):
            records["failed_update"] = updates
            return task

        def add_link(self, *args, **kwargs):
            return None

    def _raise_from_asyncio_run(coro):
        coro.close()
        raise RuntimeError("auto ingest crashed")

    monkeypatch.setattr(scheduled_module, "SessionLocal", lambda: _FakeSession(), raising=False)
    monkeypatch.setattr(
        scheduled_module,
        "reset_async_engine_pool_for_new_loop",
        lambda: None,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.services.task_center_sync_service.TaskCenterSyncService",
        _FakeTaskCenterSyncService,
    )
    monkeypatch.setattr(scheduled_module.asyncio, "run", _raise_from_asyncio_run)

    result = scheduled_module.auto_ingest_pending_files(max_files=1)

    assert result["status"] == "failed"
    assert "auto ingest crashed" in result["error"]
    assert records["failed_update"]["status"] == "failed"
    assert records["failed_update"]["error_summary"] == "auto ingest crashed"


def test_auto_ingest_pending_files_respects_global_concurrency_cap(monkeypatch):
    from backend.tasks import scheduled_tasks as scheduled_module
    original_asyncio_run = asyncio.run

    class _FakeScalarResult:
        def scalars(self):
            return self

        def all(self):
            return list(range(10))

    class _FakeSession:
        def execute(self, _stmt):
            return _FakeScalarResult()

        def close(self):
            return None

    class _FakeAsyncSession:
        async def rollback(self):
            return None

        async def close(self):
            return None

    observed = {"max_active": 0, "active": 0}

    class _FakeDataSyncService:
        def __init__(self, db):
            self.db = db

        async def get_file_sync_readiness(self, file_id, use_template_header_row=True):
            observed["active"] += 1
            observed["max_active"] = max(observed["max_active"], observed["active"])
            await asyncio.sleep(0)
            observed["active"] -= 1
            return {
                "ready": False,
                "file_id": file_id,
                "file_name": f"sample-{file_id}.xlsx",
                "template_status": "missing",
                "should_auto_sync": False,
                "message": "no template",
            }

    monkeypatch.setattr(scheduled_module, "SessionLocal", lambda: _FakeSession(), raising=False)
    monkeypatch.setattr(scheduled_module, "AUTO_INGEST_MAX_CONCURRENT", 2, raising=False)
    monkeypatch.setattr(
        scheduled_module,
        "reset_async_engine_pool_for_new_loop",
        lambda: None,
        raising=False,
    )
    monkeypatch.setattr("backend.services.data_sync_service.DataSyncService", _FakeDataSyncService)
    monkeypatch.setattr("backend.models.database.AsyncSessionLocal", lambda: _FakeAsyncSession())
    monkeypatch.setattr(scheduled_module.asyncio, "run", lambda coro: original_asyncio_run(coro))

    result = scheduled_module.auto_ingest_pending_files(max_files=10)

    assert result["status"] == "success"
    assert observed["max_active"] <= 2
