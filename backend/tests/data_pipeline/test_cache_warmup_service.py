import pytest


@pytest.mark.asyncio
async def test_cache_warmup_uses_postgresql_service_when_router_enabled(monkeypatch):
    from backend.services import cache_warmup_service

    stored = []
    called = []

    class _CacheServiceStub:
        redis_client = object()

        async def set(self, cache_type, response, **cache_params):
            stored.append((cache_type, response, cache_params))

    class _PostgresqlServiceStub:
        async def get_business_overview_kpi(self, month, platform):
            called.append(("kpi", month, platform))
            return {"gmv": 100}

        async def get_business_overview_comparison(self, granularity, target_date, platform):
            called.append(("comparison", granularity, target_date, platform))
            return {"metrics": {}}

        async def get_business_overview_shop_racing(self, granularity, target_date, group_by):
            called.append(("shop_racing", granularity, target_date, group_by))
            return []

        async def get_business_overview_traffic_ranking(self, granularity, target_date, dimension):
            called.append(("traffic_ranking", granularity, target_date, dimension))
            return []

        async def get_business_overview_inventory_backlog(self, min_days=30):
            called.append(("inventory_backlog", min_days))
            return []

        async def get_business_overview_operational_metrics(self, month, platform):
            called.append(("operational_metrics", month, platform))
            return {}

        async def get_clearance_ranking(self, limit=10):
            called.append(("clearance_ranking", limit))
            return []

    monkeypatch.setenv("USE_POSTGRESQL_DASHBOARD_ROUTER", "true")
    monkeypatch.setattr(
        "backend.services.cache_warmup_service.get_cache_service",
        lambda: _CacheServiceStub(),
    )
    monkeypatch.setattr(
        "backend.services.cache_warmup_service.get_postgresql_dashboard_service",
        lambda: _PostgresqlServiceStub(),
    )

    result = await cache_warmup_service.run_dashboard_cache_warmup()

    assert result["ok"] == 7
    assert result["failed"] == 0
    assert len(stored) == 7
    assert any(item[0] == "dashboard_kpi" for item in stored)
    assert any(call[0] == "kpi" for call in called)
    assert any(call[0] == "clearance_ranking" for call in called)


@pytest.mark.asyncio
async def test_cache_warmup_never_uses_metabase_fallback(monkeypatch):
    from backend.services import cache_warmup_service

    stored = []

    class _CacheServiceStub:
        redis_client = object()

        async def set(self, cache_type, response, **cache_params):
            stored.append((cache_type, response, cache_params))

    monkeypatch.setenv("USE_POSTGRESQL_DASHBOARD_ROUTER", "false")
    monkeypatch.setattr(
        "backend.services.cache_warmup_service.get_cache_service",
        lambda: _CacheServiceStub(),
    )

    with pytest.raises(RuntimeError, match="Metabase fallback has been retired"):
        await cache_warmup_service.run_dashboard_cache_warmup()

    assert stored == []
