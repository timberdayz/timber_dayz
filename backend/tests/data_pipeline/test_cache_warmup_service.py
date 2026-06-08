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
        async def get_business_overview_kpi(
            self,
            month,
            platform,
            granularity="monthly",
            target_date=None,
            shop_id=None,
        ):
            called.append(("kpi", month, platform, granularity, target_date))
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

        async def get_business_overview_inventory_backlog(
            self,
            min_days,
            limit,
            granularity=None,
            target_date=None,
        ):
            called.append(("inventory_backlog", min_days, limit))
            return []

        async def get_business_overview_operational_metrics(self, month, platform, shop_id=None):
            called.append(("operational_metrics", month, platform))
            return {}

        async def get_clearance_ranking(self, limit=10, granularity=None, target_date=None):
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

    assert result["ok"] == 8
    assert result["failed"] == 0
    assert len(stored) == 8
    assert any(item[0] == "dashboard_business_overview_bootstrap" for item in stored)
    assert any(item[0] == "dashboard_kpi" for item in stored)
    assert any(call[0] == "kpi" for call in called)
    assert ("inventory_backlog", 30, 20) in called
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

    with pytest.raises(RuntimeError, match="Legacy non-PostgreSQL warmup path has been retired"):
        await cache_warmup_service.run_dashboard_cache_warmup()

    assert stored == []
