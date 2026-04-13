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
