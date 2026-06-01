import asyncio


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

    def _fake_async_run(coro):
        return original_asyncio_run(coro)

    monkeypatch.setattr(scheduled_module.asyncio, "run", _fake_async_run)

    result = scheduled_module.auto_ingest_pending_files(max_files=1)

    assert result["status"] == "success"
    assert result["summary"]["skipped"] == 1
    assert result["summary"]["skipped_template_update"] == 1


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
