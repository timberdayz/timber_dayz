import asyncio

import pytest

from backend.utils.events import DataIngestedEvent


@pytest.mark.asyncio
async def test_data_ingested_event_triggers_postgresql_refresh_enqueue(monkeypatch):
    from backend.services.event_listeners import event_listener

    captured = {}
    scheduled = {}

    def _fake_enqueue_refresh(event):
        captured["event"] = event
        async def _noop():
            return None
        return _noop()

    def _fake_create_task(coro):
        scheduled["coro"] = coro
        coro.close()
        return "task-created"

    monkeypatch.setattr(
        "backend.services.event_listeners.enqueue_refresh_for_data_ingested_event",
        _fake_enqueue_refresh,
    )
    monkeypatch.setattr(
        "backend.services.event_listeners.asyncio.create_task",
        _fake_create_task,
    )

    event = DataIngestedEvent(
        file_id=1,
        platform_code="shopee",
        data_domain="orders",
        granularity="daily",
        row_count=10,
    )

    event_listener.handle_data_ingested(event)

    assert scheduled["coro"] is not None
    assert captured["event"] == event


@pytest.mark.asyncio
async def test_inventory_data_ingested_event_triggers_inventory_age_refresh(
    monkeypatch,
):
    from backend.services.event_listeners import (
        run_pipeline_refresh_for_data_ingested_event,
    )

    calls = {"pipeline": 0, "inventory_age": 0}

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def commit(self):
            return None

    class _FakeAsyncSessionLocal:
        def __call__(self):
            return _FakeSession()

    class _FakeInventoryAgeRefreshService:
        def __init__(self, db):
            self.db = db

        async def refresh(self, force_full: bool = False):
            calls["inventory_age"] += 1
            assert force_full is False
            return {"mode": "incremental", "replayed_key_count": 1}

    async def _fake_execute_refresh_plan(*args, **kwargs):
        calls["pipeline"] += 1
        return "run-1"

    monkeypatch.setattr(
        "backend.services.event_listeners.AsyncSessionLocal",
        _FakeAsyncSessionLocal(),
    )
    monkeypatch.setattr(
        "backend.services.event_listeners.execute_refresh_plan",
        _fake_execute_refresh_plan,
    )
    monkeypatch.setattr(
        "backend.services.event_listeners.InventoryAgeRefreshService",
        _FakeInventoryAgeRefreshService,
    )

    event = DataIngestedEvent(
        file_id=99,
        platform_code="miaoshou",
        data_domain="inventory",
        granularity="snapshot",
        row_count=10,
    )

    run_id = await run_pipeline_refresh_for_data_ingested_event(event)

    assert run_id == "run-1"
    assert calls["pipeline"] == 1
    assert calls["inventory_age"] == 1


@pytest.mark.asyncio
async def test_data_ingested_refresh_runs_serially_within_same_process(
    monkeypatch,
):
    from backend.services.event_listeners import run_pipeline_refresh_for_data_ingested_event

    state = {"active": 0, "max_active": 0}

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def commit(self):
            return None

    class _FakeAsyncSessionLocal:
        def __call__(self):
            return _FakeSession()

    async def _fake_execute_refresh_plan(*args, **kwargs):
        state["active"] += 1
        state["max_active"] = max(state["max_active"], state["active"])
        await asyncio.sleep(0.01)
        state["active"] -= 1
        return "run-serial"

    monkeypatch.setattr(
        "backend.services.event_listeners.AsyncSessionLocal",
        _FakeAsyncSessionLocal(),
    )
    monkeypatch.setattr(
        "backend.services.event_listeners.execute_refresh_plan",
        _fake_execute_refresh_plan,
    )

    event_a = DataIngestedEvent(
        file_id=1,
        platform_code="shopee",
        data_domain="services",
        granularity="daily",
        row_count=1,
    )
    event_b = DataIngestedEvent(
        file_id=2,
        platform_code="shopee",
        data_domain="services",
        granularity="daily",
        row_count=1,
    )

    await asyncio.gather(
        run_pipeline_refresh_for_data_ingested_event(event_a),
        run_pipeline_refresh_for_data_ingested_event(event_b),
    )

    assert state["max_active"] == 1
