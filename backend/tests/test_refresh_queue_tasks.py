import asyncio

import pytest


def test_process_refresh_queue_task_returns_skipped_when_queue_empty(monkeypatch):
    from backend.tasks import refresh_queue_tasks as task_module

    calls = []
    original_asyncio_run = asyncio.run

    class _FakeSession:
        async def close(self):
            return None

    class _FakeQueueService:
        def __init__(self, db):
            self.db = db

        async def claim_next_refresh_task(self):
            return None

    monkeypatch.setattr(task_module, "AsyncSessionLocal", lambda: _FakeSession(), raising=False)
    monkeypatch.setattr(task_module, "RefreshQueueService", _FakeQueueService, raising=False)
    monkeypatch.setattr(task_module, "reset_async_engine_pool_for_new_loop", lambda: calls.append("reset"), raising=False)
    monkeypatch.setattr(
        task_module.asyncio,
        "run",
        lambda coro: (calls.append("run"), original_asyncio_run(coro))[1],
    )

    result = task_module.process_refresh_queue_task.run()

    assert result["status"] == "skipped"
    assert result["reason"] == "no_pending_refresh_queue_task"
    assert calls[:2] == ["reset", "run"]


@pytest.mark.asyncio
async def test_process_refresh_queue_task_claims_executes_and_completes(monkeypatch):
    from backend.tasks import refresh_queue_tasks as task_module

    calls = []

    class _FakeTask:
        id = 1
        job_id = "job-1"
        trigger_type = "data_ingested"
        pipeline_name = "data_ingested_refresh"
        targets_json = ["semantic.fact_services_atomic"]
        context_json = {"file_id": 1, "data_domain": "services"}

    class _FakeSession:
        async def commit(self):
            return None

        async def rollback(self):
            return None

        async def close(self):
            return None

    class _FakeQueueService:
        def __init__(self, db):
            self.db = db

        async def claim_next_refresh_task(self):
            calls.append("claim")
            return _FakeTask()

        async def mark_completed(self, task_id: int):
            calls.append(("completed", task_id))
            return None

        async def mark_failed(self, task_id: int, error_message: str):
            calls.append(("failed", task_id, error_message))
            return None

    async def _fake_execute_refresh_plan(*args, **kwargs):
        calls.append(("execute", kwargs["targets"], kwargs["context"]))
        return "run-1"

    monkeypatch.setattr(task_module, "AsyncSessionLocal", lambda: _FakeSession(), raising=False)
    monkeypatch.setattr(task_module, "RefreshQueueService", _FakeQueueService, raising=False)
    monkeypatch.setattr(task_module, "execute_refresh_plan", _fake_execute_refresh_plan, raising=False)

    result = await task_module._async_process_refresh_queue_task()

    assert result["status"] == "success"
    assert result["job_id"] == "job-1"
    assert calls[0] == "claim"
    assert calls[1][0] == "execute"
    assert calls[2] == ("completed", 1)


@pytest.mark.asyncio
async def test_process_refresh_queue_task_marks_failed_on_exception(monkeypatch):
    from backend.tasks import refresh_queue_tasks as task_module

    calls = []

    class _FakeTask:
        id = 7
        job_id = "job-7"
        trigger_type = "data_ingested"
        pipeline_name = "data_ingested_refresh"
        targets_json = ["semantic.fact_services_atomic"]
        context_json = {"file_id": 7, "data_domain": "services"}

    class _FakeSession:
        async def commit(self):
            return None

        async def rollback(self):
            return None

        async def close(self):
            return None

    class _FakeQueueService:
        def __init__(self, db):
            self.db = db

        async def claim_next_refresh_task(self):
            return _FakeTask()

        async def mark_completed(self, task_id: int):
            calls.append(("completed", task_id))
            return None

        async def mark_failed(self, task_id: int, error_message: str):
            calls.append(("failed", task_id, error_message))
            return None

    async def _fake_execute_refresh_plan(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(task_module, "AsyncSessionLocal", lambda: _FakeSession(), raising=False)
    monkeypatch.setattr(task_module, "RefreshQueueService", _FakeQueueService, raising=False)
    monkeypatch.setattr(task_module, "execute_refresh_plan", _fake_execute_refresh_plan, raising=False)

    result = await task_module._async_process_refresh_queue_task()

    assert result["status"] == "failed"
    assert calls[0][0] == "failed"
    assert calls[0][1] == 7
    assert "boom" in calls[0][2]
