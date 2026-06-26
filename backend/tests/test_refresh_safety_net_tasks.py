import pytest


@pytest.mark.asyncio
async def test_refresh_safety_net_enqueues_repair_for_drifted_dashboard_assets(monkeypatch):
    from backend.tasks import refresh_queue_tasks as task_module

    calls = []

    class _FakeSession:
        async def close(self):
            calls.append("close")

    class _FakeQueueService:
        def __init__(self, db):
            self.db = db

        async def recover_stale_running_tasks(self, timeout_seconds: int):
            calls.append(("recover", timeout_seconds))
            return 1

        async def enqueue_refresh(self, *, trigger_type, pipeline_name, targets, context=None):
            calls.append(
                (
                    "enqueue",
                    trigger_type,
                    pipeline_name,
                    tuple(targets),
                    context,
                )
            )
            return type("Task", (), {"job_id": "refresh-safety-net-1"})()

    async def _fake_inspect_dashboard_assets(db):
        calls.append("inspect")
        return {
            "ready": False,
            "modules": {
                "business_overview": {
                    "status": "drift",
                    "core_missing_objects": ["api.business_overview_kpi_module"],
                },
                "clearance_ranking": {
                    "status": "ready",
                },
            },
        }

    monkeypatch.setattr(task_module, "AsyncSessionLocal", lambda: _FakeSession(), raising=False)
    monkeypatch.setattr(task_module, "RefreshQueueService", _FakeQueueService, raising=False)
    monkeypatch.setattr(task_module, "inspect_dashboard_assets", _fake_inspect_dashboard_assets, raising=False)

    result = await task_module._async_dashboard_refresh_safety_net()

    assert result["status"] == "success"
    assert result["recovered_stale_tasks"] == 1
    assert result["enqueued_repairs"] == 1
    enqueue_call = next(call for call in calls if isinstance(call, tuple) and call[0] == "enqueue")
    assert enqueue_call[1] == "safety_net"
    assert enqueue_call[2] == "dashboard_safety_net_repair"
    assert "api.business_overview_kpi_module" in enqueue_call[3]
    assert enqueue_call[4]["module_name"] == "business_overview"
