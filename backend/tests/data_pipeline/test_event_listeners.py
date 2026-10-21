import asyncio

import pytest

from backend.utils.events import DataIngestedEvent


@pytest.mark.asyncio
async def test_data_ingested_event_triggers_postgresql_refresh_enqueue(monkeypatch):
    from backend.services.event_listeners import event_listener

    captured = {}
    completed = {}

    async def _fake_enqueue_refresh(event):
        captured["event"] = event
        completed["done"] = True
        return "refresh-job-1"

    monkeypatch.setattr(
        "backend.services.event_listeners.enqueue_refresh_for_data_ingested_event",
        _fake_enqueue_refresh,
    )

    event = DataIngestedEvent(
        file_id=1,
        platform_code="shopee",
        data_domain="orders",
        granularity="daily",
        row_count=10,
    )

    await event_listener.handle_data_ingested_async(event)

    # 入队必须被 await 到完成:早先用 create_task 排进事件循环,调用方
    # asyncio.run(...) 收尾时会把未完成的 task 取消,刷新从未真正入队。
    assert completed.get("done") is True
    assert captured["event"] == event


@pytest.mark.asyncio
async def test_data_ingested_enqueue_failure_does_not_break_dispatch(monkeypatch):
    """入队失败只告警,不能把整个 DATA_INGESTED 派发打断。"""
    from backend.services.event_listeners import event_listener

    async def _fake_enqueue_refresh(event):
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr(
        "backend.services.event_listeners.enqueue_refresh_for_data_ingested_event",
        _fake_enqueue_refresh,
    )

    event = DataIngestedEvent(
        file_id=2,
        platform_code="shopee",
        data_domain="orders",
        granularity="daily",
        row_count=10,
    )

    result = await event_listener.handle_data_ingested_async(event)

    # source_table_name 为空 -> 没有云同步分支, 返回 None
    assert result is None


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


def test_data_ingested_targets_are_registered_refresh_targets():
    from backend.services.event_listeners import DATA_INGESTED_PIPELINE_TARGETS
    from backend.services.data_pipeline.refresh_registry import SQL_TARGET_PATHS

    for domain, targets in DATA_INGESTED_PIPELINE_TARGETS.items():
        for target in targets:
            assert target in SQL_TARGET_PATHS, f"{domain} target must be registered: {target}"


def test_business_overview_ingested_targets_rebuild_cascade_dependents():
    from backend.services.event_listeners import determine_pipeline_targets_for_data_ingested

    required_targets = {
        "mart.platform_day_kpi",
        "mart.platform_week_kpi",
        "api.business_overview_comparison_platform_module",
        "api.business_overview_shop_racing_monthly_module",
    }

    for data_domain in ("orders", "analytics", "traffic"):
        event = DataIngestedEvent(
            file_id=None,
            platform_code=None,
            data_domain=data_domain,
            granularity=None,
            source_table_name=f"fact_shopee_{data_domain}_daily",
            row_count=1,
        )

        targets = set(determine_pipeline_targets_for_data_ingested(event))

        missing_targets = required_targets - targets
        assert not missing_targets, f"{data_domain} missing cascade dependents: {missing_targets}"
