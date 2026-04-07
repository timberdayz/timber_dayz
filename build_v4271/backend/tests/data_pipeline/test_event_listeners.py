import asyncio

import pytest

from backend.utils.events import DataIngestedEvent


@pytest.mark.asyncio
async def test_data_ingested_event_triggers_postgresql_refresh(monkeypatch):
    from backend.services.event_listeners import event_listener

    captured = {}
    scheduled = {}

    def _fake_run_pipeline_refresh(event):
        captured["event"] = event
        async def _noop():
            return None
        return _noop()

    def _fake_create_task(coro):
        scheduled["coro"] = coro
        coro.close()
        return "task-created"

    monkeypatch.setattr(
        "backend.services.event_listeners.run_pipeline_refresh_for_data_ingested_event",
        _fake_run_pipeline_refresh,
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
