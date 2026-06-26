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

        async def recover_stale_running_tasks(self, timeout_seconds: int):
            calls.append(("recover", timeout_seconds))
            return 0

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

        async def recover_stale_running_tasks(self, timeout_seconds: int):
            calls.append(("recover", timeout_seconds))
            return 0

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
        return {"run_id": "run-1", "status": "success", "failed_targets": []}

    monkeypatch.setattr(task_module, "AsyncSessionLocal", lambda: _FakeSession(), raising=False)
    monkeypatch.setattr(task_module, "RefreshQueueService", _FakeQueueService, raising=False)
    monkeypatch.setattr(task_module, "execute_refresh_plan", _fake_execute_refresh_plan, raising=False)

    result = await task_module._async_process_refresh_queue_task()

    assert result["status"] == "success"
    assert result["job_id"] == "job-1"
    assert result["run_id"] == "run-1"
    assert calls[0][0] == "recover"
    assert calls[1] == "claim"
    assert calls[2][0] == "execute"
    assert calls[3] == ("completed", 1)


@pytest.mark.asyncio
async def test_process_refresh_queue_task_invalidates_dashboard_cache_after_business_refresh(monkeypatch):
    from backend.tasks import refresh_queue_tasks as task_module

    calls = []

    class _FakeTask:
        id = 11
        job_id = "job-11"
        trigger_type = "cloud_sync"
        pipeline_name = "data_ingested_refresh"
        targets_json = ["api.business_overview_kpi_module"]
        context_json = {"source_table_name": "fact_shopee_orders_daily", "data_domain": "orders"}

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

        async def recover_stale_running_tasks(self, timeout_seconds: int):
            return 0

        async def claim_next_refresh_task(self):
            return _FakeTask()

        async def mark_completed(self, task_id: int):
            calls.append(("completed", task_id))

        async def mark_failed(self, task_id: int, error_message: str):
            calls.append(("failed", task_id, error_message))

    class _FakeCacheService:
        async def invalidate_dashboard_business_overview(self):
            calls.append("invalidate_business_overview")
            return 3

        async def invalidate(self, cache_type):
            calls.append(("invalidate", cache_type))
            return 0

    async def _fake_execute_refresh_plan(*args, **kwargs):
        return {"run_id": "run-11", "status": "success", "failed_targets": []}

    monkeypatch.setattr(task_module, "AsyncSessionLocal", lambda: _FakeSession(), raising=False)
    monkeypatch.setattr(task_module, "RefreshQueueService", _FakeQueueService, raising=False)
    monkeypatch.setattr(task_module, "execute_refresh_plan", _fake_execute_refresh_plan, raising=False)
    monkeypatch.setattr(task_module, "get_cache_service", lambda: _FakeCacheService(), raising=False)

    result = await task_module._async_process_refresh_queue_task()

    assert result["status"] == "success"
    assert "invalidate_business_overview" in calls
    assert ("completed", 11) in calls


@pytest.mark.asyncio
async def test_process_refresh_queue_task_invalidates_clearance_cache(monkeypatch):
    from backend.tasks import refresh_queue_tasks as task_module

    calls = []

    class _FakeTask:
        id = 12
        job_id = "job-12"
        trigger_type = "cloud_sync"
        pipeline_name = "data_ingested_refresh"
        targets_json = ["api.clearance_ranking_module"]
        context_json = {"source_table_name": "fact_shopee_products_daily", "data_domain": "products"}

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

        async def recover_stale_running_tasks(self, timeout_seconds: int):
            return 0

        async def claim_next_refresh_task(self):
            return _FakeTask()

        async def mark_completed(self, task_id: int):
            calls.append(("completed", task_id))

        async def mark_failed(self, task_id: int, error_message: str):
            calls.append(("failed", task_id, error_message))

    class _FakeCacheService:
        async def invalidate_dashboard_business_overview(self):
            calls.append("invalidate_business_overview")
            return 0

        async def invalidate(self, cache_type):
            calls.append(("invalidate", cache_type))
            return 2

    async def _fake_execute_refresh_plan(*args, **kwargs):
        return {"run_id": "run-12", "status": "success", "failed_targets": []}

    monkeypatch.setattr(task_module, "AsyncSessionLocal", lambda: _FakeSession(), raising=False)
    monkeypatch.setattr(task_module, "RefreshQueueService", _FakeQueueService, raising=False)
    monkeypatch.setattr(task_module, "execute_refresh_plan", _fake_execute_refresh_plan, raising=False)
    monkeypatch.setattr(task_module, "get_cache_service", lambda: _FakeCacheService(), raising=False)

    result = await task_module._async_process_refresh_queue_task()

    assert result["status"] == "success"
    assert ("invalidate", "dashboard_clearance_ranking") in calls
    assert "invalidate_business_overview" not in calls


@pytest.mark.asyncio
async def test_process_refresh_queue_task_repairs_drifted_dashboard_assets_before_refresh(monkeypatch):
    from backend.tasks import refresh_queue_tasks as task_module

    calls = []

    class _FakeTask:
        id = 13
        job_id = "job-13"
        trigger_type = "cloud_sync"
        pipeline_name = "data_ingested_refresh"
        targets_json = ["api.business_overview_kpi_module"]
        context_json = {"source_table_name": "fact_shopee_orders_daily", "data_domain": "orders"}

    class _FakeSession:
        async def commit(self):
            calls.append("commit")

        async def rollback(self):
            return None

        async def close(self):
            return None

    class _FakeQueueService:
        def __init__(self, db):
            self.db = db

        async def recover_stale_running_tasks(self, timeout_seconds: int):
            return 0

        async def claim_next_refresh_task(self):
            return _FakeTask()

        async def mark_completed(self, task_id: int):
            calls.append(("completed", task_id))

        async def mark_failed(self, task_id: int, error_message: str):
            calls.append(("failed", task_id, error_message))

    async def _fake_inspect_dashboard_assets(db):
        calls.append("inspect")
        return {
            "modules": {
                "business_overview": {
                    "status": "drift",
                    "core_missing_objects": ["api.business_overview_kpi_module"],
                }
            }
        }

    async def _fake_bootstrap_dashboard_assets_if_needed(db, wait_for_lock, module):
        calls.append(("bootstrap", wait_for_lock, module))
        return {"modules": {module: {"status": "ready"}}}

    async def _fake_execute_refresh_plan(*args, **kwargs):
        calls.append("execute")
        return {"run_id": "run-13", "status": "success", "failed_targets": []}

    monkeypatch.setattr(task_module, "AsyncSessionLocal", lambda: _FakeSession(), raising=False)
    monkeypatch.setattr(task_module, "RefreshQueueService", _FakeQueueService, raising=False)
    monkeypatch.setattr(task_module, "inspect_dashboard_assets", _fake_inspect_dashboard_assets, raising=False)
    monkeypatch.setattr(task_module, "bootstrap_dashboard_assets_if_needed", _fake_bootstrap_dashboard_assets_if_needed, raising=False)
    monkeypatch.setattr(task_module, "execute_refresh_plan", _fake_execute_refresh_plan, raising=False)

    result = await task_module._async_process_refresh_queue_task()

    assert result["status"] == "success"
    assert ("bootstrap", True, "business_overview") in calls
    assert calls.index(("bootstrap", True, "business_overview")) < calls.index("execute")


@pytest.mark.asyncio
async def test_process_refresh_queue_task_repairs_after_refresh_validation_failure(monkeypatch):
    from backend.tasks import refresh_queue_tasks as task_module

    calls = []

    class _FakeTask:
        id = 14
        job_id = "job-14"
        trigger_type = "cloud_sync"
        pipeline_name = "data_ingested_refresh"
        targets_json = ["api.business_overview_kpi_module"]
        context_json = {
            "source_table_name": "fact_shopee_orders_monthly",
            "data_domain": "orders",
            "written_rows": 10,
        }

    class _FakeSession:
        async def commit(self):
            calls.append("commit")

        async def rollback(self):
            return None

        async def close(self):
            return None

    class _FakeQueueService:
        def __init__(self, db):
            self.db = db

        async def recover_stale_running_tasks(self, timeout_seconds: int):
            return 0

        async def claim_next_refresh_task(self):
            return _FakeTask()

        async def mark_completed(self, task_id: int):
            calls.append(("completed", task_id))

        async def mark_failed(self, task_id: int, error_message: str):
            calls.append(("failed", task_id, error_message))

    class _Report:
        def __init__(self, status, missing_objects=None, repair_attempted=False):
            self.status = status
            self.missing_objects = missing_objects or []
            self.stale_targets = []
            self.modules = ["business_overview"]
            self.repair_attempted = repair_attempted
            self.error_message = None

        def is_success(self):
            return self.status == "success"

        def to_error_message(self):
            return "missing_objects:" + ",".join(self.missing_objects)

    validation_reports = [
        _Report("failed", ["api.business_overview_kpi_module"]),
        _Report("failed", ["api.business_overview_kpi_module"], repair_attempted=True),
        _Report("success", repair_attempted=True),
    ]

    async def _fake_execute_refresh_plan(*args, **kwargs):
        calls.append(("execute", tuple(kwargs["targets"])))
        return {"run_id": f"run-{len([call for call in calls if call[0] == 'execute'])}", "status": "success", "failed_targets": []}

    async def _fake_validate_refresh_result(*args, **kwargs):
        calls.append("validate")
        return validation_reports.pop(0)

    async def _fake_bootstrap_dashboard_assets_if_needed(db, wait_for_lock, module):
        calls.append(("bootstrap", wait_for_lock, module))
        return {"modules": {module: {"status": "ready"}}}

    monkeypatch.setattr(task_module, "AsyncSessionLocal", lambda: _FakeSession(), raising=False)
    monkeypatch.setattr(task_module, "RefreshQueueService", _FakeQueueService, raising=False)
    monkeypatch.setattr(task_module, "execute_refresh_plan", _fake_execute_refresh_plan, raising=False)
    monkeypatch.setattr(task_module, "validate_refresh_result", _fake_validate_refresh_result, raising=False)
    monkeypatch.setattr(task_module, "bootstrap_dashboard_assets_if_needed", _fake_bootstrap_dashboard_assets_if_needed, raising=False)

    result = await task_module._async_process_refresh_queue_task()

    assert result["status"] == "success"
    assert calls.count("validate") == 3
    assert len([call for call in calls if isinstance(call, tuple) and call[0] == "execute"]) == 2
    assert ("bootstrap", True, "business_overview") in calls
    assert ("completed", 14) in calls
    assert not any(call[0] == "failed" for call in calls if isinstance(call, tuple))


@pytest.mark.asyncio
async def test_process_refresh_queue_task_fails_when_post_refresh_repair_cannot_validate(monkeypatch):
    from backend.tasks import refresh_queue_tasks as task_module

    calls = []

    class _FakeTask:
        id = 15
        job_id = "job-15"
        trigger_type = "cloud_sync"
        pipeline_name = "data_ingested_refresh"
        targets_json = ["api.business_overview_kpi_module"]
        context_json = {"source_table_name": "fact_shopee_orders_monthly", "data_domain": "orders"}

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

        async def recover_stale_running_tasks(self, timeout_seconds: int):
            return 0

        async def claim_next_refresh_task(self):
            return _FakeTask()

        async def mark_completed(self, task_id: int):
            calls.append(("completed", task_id))

        async def mark_failed(self, task_id: int, error_message: str):
            calls.append(("failed", task_id, error_message))

    class _Report:
        status = "failed"
        missing_objects = ["api.business_overview_kpi_module"]
        stale_targets = []
        modules = ["business_overview"]
        repair_attempted = False
        error_message = None

        def is_success(self):
            return False

        def to_error_message(self):
            return "missing_objects:api.business_overview_kpi_module"

    async def _fake_execute_refresh_plan(*args, **kwargs):
        return {"run_id": "run-15", "status": "success", "failed_targets": []}

    async def _fake_validate_refresh_result(*args, **kwargs):
        calls.append("validate")
        return _Report()

    async def _fake_bootstrap_dashboard_assets_if_needed(db, wait_for_lock, module):
        calls.append(("bootstrap", wait_for_lock, module))
        return {"modules": {module: {"status": "drift"}}}

    monkeypatch.setattr(task_module, "AsyncSessionLocal", lambda: _FakeSession(), raising=False)
    monkeypatch.setattr(task_module, "RefreshQueueService", _FakeQueueService, raising=False)
    monkeypatch.setattr(task_module, "execute_refresh_plan", _fake_execute_refresh_plan, raising=False)
    monkeypatch.setattr(task_module, "validate_refresh_result", _fake_validate_refresh_result, raising=False)
    monkeypatch.setattr(task_module, "bootstrap_dashboard_assets_if_needed", _fake_bootstrap_dashboard_assets_if_needed, raising=False)

    result = await task_module._async_process_refresh_queue_task()

    assert result["status"] == "failed"
    assert ("bootstrap", True, "business_overview") in calls
    assert calls[-1][0] == "failed"
    assert "missing_objects:api.business_overview_kpi_module" in calls[-1][2]


@pytest.mark.asyncio
async def test_process_refresh_queue_task_marks_failed_on_partial_failed_run(monkeypatch):
    from backend.tasks import refresh_queue_tasks as task_module

    calls = []

    class _FakeTask:
        id = 3
        job_id = "job-3"
        trigger_type = "data_ingested"
        pipeline_name = "data_ingested_refresh"
        targets_json = ["api.business_overview_kpi_module"]
        context_json = {"file_id": 3, "data_domain": "orders"}

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

        async def recover_stale_running_tasks(self, timeout_seconds: int):
            calls.append(("recover", timeout_seconds))
            return 0

        async def claim_next_refresh_task(self):
            return _FakeTask()

        async def mark_completed(self, task_id: int):
            calls.append(("completed", task_id))
            return None

        async def mark_failed(self, task_id: int, error_message: str):
            calls.append(("failed", task_id, error_message))
            return None

    async def _fake_execute_refresh_plan(*args, **kwargs):
        return {
            "run_id": "run-3",
            "status": "partial_failed",
            "failed_targets": ["semantic.fact_orders_monthly_atomic_mv"],
        }

    monkeypatch.setattr(task_module, "AsyncSessionLocal", lambda: _FakeSession(), raising=False)
    monkeypatch.setattr(task_module, "RefreshQueueService", _FakeQueueService, raising=False)
    monkeypatch.setattr(task_module, "execute_refresh_plan", _fake_execute_refresh_plan, raising=False)

    result = await task_module._async_process_refresh_queue_task()

    assert result["status"] == "failed"
    assert result["job_id"] == "job-3"
    assert result["run_id"] == "run-3"
    assert calls[0][0] == "recover"
    assert calls[1][0] == "failed"
    assert calls[1][1] == 3
    assert "partial_failed" in calls[1][2]
    assert "semantic.fact_orders_monthly_atomic_mv" in calls[1][2]


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

        async def recover_stale_running_tasks(self, timeout_seconds: int):
            calls.append(("recover", timeout_seconds))
            return 0

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
    assert calls[0][0] == "recover"
    assert calls[1][0] == "failed"
    assert calls[1][1] == 7
    assert "boom" in calls[1][2]
