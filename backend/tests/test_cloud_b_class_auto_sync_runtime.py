import asyncio

import pytest

from backend.services.cloud_b_class_auto_sync_runtime import (
    CloudBClassAutoSyncRuntime,
    should_enable_cloud_sync_worker,
)


class FakeWorker:
    def __init__(self):
        self.calls = []

    def run_one(self, worker_id: str):
        self.calls.append(worker_id)
        return None


@pytest.mark.asyncio
async def test_runtime_start_and_stop_updates_health():
    worker = FakeWorker()
    runtime = CloudBClassAutoSyncRuntime(
        worker_factory=lambda: worker,
        poll_interval_seconds=0.01,
        worker_id="worker-1",
    )

    await runtime.start()
    await asyncio.sleep(0.03)
    health_running = runtime.get_health()
    await runtime.stop()
    health_stopped = runtime.get_health()

    assert health_running["status"] == "running"
    assert health_running["worker_id"] == "worker-1"
    assert worker.calls
    assert health_stopped["status"] == "stopped"


@pytest.mark.asyncio
async def test_runtime_reports_not_configured_without_worker_factory():
    runtime = CloudBClassAutoSyncRuntime(
        worker_factory=None,
        poll_interval_seconds=0.01,
        worker_id="worker-1",
    )

    started = await runtime.start()
    health = runtime.get_health()

    assert started is False
    assert health["status"] == "not_configured"


def test_should_enable_cloud_sync_worker():
    assert should_enable_cloud_sync_worker("true", True, "local") is True
    assert should_enable_cloud_sync_worker("false", True, "local") is False
    assert should_enable_cloud_sync_worker("true", False, "local") is False
    assert should_enable_cloud_sync_worker("true", True, "cloud") is False


@pytest.mark.asyncio
async def test_runtime_stop_closes_worker_factory_when_supported():
    worker = FakeWorker()

    class FakeFactory:
        def __init__(self):
            self.closed = False

        def __call__(self):
            return worker

        def close(self):
            self.closed = True

    factory = FakeFactory()
    runtime = CloudBClassAutoSyncRuntime(
        worker_factory=factory,
        poll_interval_seconds=0.01,
        worker_id="worker-1",
    )

    await runtime.start()
    await asyncio.sleep(0.03)
    await runtime.stop()

    assert factory.closed is True
