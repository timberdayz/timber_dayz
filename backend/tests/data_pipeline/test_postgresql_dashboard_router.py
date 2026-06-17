import asyncio
import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from backend.domains.business.routers.dashboard_api_postgresql import (
    _require_dashboard_assets_ready,
    get_business_overview_bootstrap_postgresql,
    get_business_overview_comparison_postgresql,
    get_business_overview_inventory_backlog_postgresql,
    get_business_overview_kpi_postgresql,
    get_business_overview_operational_metrics_postgresql,
    get_business_overview_shop_racing_postgresql,
    get_business_overview_traffic_ranking_postgresql,
    get_clearance_ranking_postgresql,
    router,
)


@pytest.fixture(autouse=True)
def _bridge_compat_dashboard_service_patch(monkeypatch):
    import backend.domains.business.routers.dashboard_api_postgresql as actual_router
    import backend.routers.dashboard_api_postgresql as compat_router

    monkeypatch.setattr(
        actual_router,
        "get_postgresql_dashboard_service",
        lambda: compat_router.get_postgresql_dashboard_service(),
    )


def _make_request(path: str):
    app = SimpleNamespace(
        state=SimpleNamespace(
            dashboard_assets_report={
                "ready": True,
                "modules": {
                    "business_overview": {
                        "status": "ready",
                        "ready": True,
                    },
                    "clearance": {
                        "status": "ready",
                        "ready": True,
                    },
                    "b_cost": {
                        "status": "ready",
                        "ready": True,
                    },
                }
            }
        )
    )
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 8001),
            "app": app,
        }
    )


def _make_dashboard_not_ready_request(path: str):
    app = SimpleNamespace(
        state=SimpleNamespace(
            dashboard_assets_report={
                "ready": False,
                "missing_schemas": [],
                "missing_objects": [],
                "assets_drift": True,
                "assets_fingerprint_expected": "expected",
                "assets_fingerprint_last": "actual",
            }
        )
    )
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 8001),
            "app": app,
        }
    )


def _make_cached_request(path: str, cache_service):
    app = SimpleNamespace(
        state=SimpleNamespace(
            dashboard_assets_report={"ready": True},
            cache_service=cache_service,
        )
    )
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 8001),
            "app": app,
        }
    )


def test_postgresql_kpi_route_returns_service_payload(monkeypatch):
    class _ServiceStub:
        async def get_business_overview_kpi(
            self,
            month=None,
            platform=None,
            granularity="monthly",
            target_date=None,
            shop_id=None,
        ):
            return {
                "gmv": 123,
                "order_count": 10,
                "visitor_count": 200,
                "conversion_rate": 5,
                "avg_order_value": 12.3,
                "attach_rate": 1.2,
                "labor_efficiency": 0,
            }

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )
    monkeypatch.setattr(
        "backend.domains.business.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_business_overview_kpi_postgresql(
            request=_make_request("/api/dashboard/business-overview/kpi"),
            period_key="2026-03-01",
            platform_code=None,
            shop_id=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert body["data"]["gmv"] == 123


def test_postgresql_kpi_route_serializes_freshness_dates(monkeypatch):
    class _ServiceStub:
        async def get_business_overview_kpi(
            self,
            month=None,
            platform=None,
            granularity="monthly",
            target_date=None,
            shop_id=None,
        ):
            return {
                "gmv": 123,
                "order_count": 10,
                "visitor_count": 200,
                "conversion_rate": 5,
                "avg_order_value": 12.3,
                "attach_rate": 1.2,
                "labor_efficiency": 0,
            }

        async def get_business_overview_data_freshness(self, **_kwargs):
            return {
                "orders": {
                    "period_start_date": date(2026, 6, 1),
                    "period_end_date": date(2026, 6, 30),
                    "latest_ingest_timestamp": datetime(2026, 6, 17, 12, 30, tzinfo=timezone.utc),
                },
                "traffic": {
                    "period_start_date": date(2026, 6, 1),
                    "period_end_date": date(2026, 6, 30),
                    "latest_metric_date": date(2026, 6, 30),
                },
                "is_stale": False,
                "warnings": [],
            }

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )
    monkeypatch.setattr(
        "backend.domains.business.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_business_overview_kpi_postgresql(
            request=_make_request("/api/dashboard/business-overview/kpi"),
            period_key="2026-06-01",
            platform_code=None,
            shop_id=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    freshness = body["meta"]["data_freshness"]
    assert freshness["orders"]["period_start_date"] == "2026-06-01"
    assert freshness["orders"]["period_end_date"] == "2026-06-30"
    assert freshness["orders"]["latest_ingest_timestamp"] == "2026-06-17T12:30:00+00:00"


def test_postgresql_kpi_route_accepts_granularity_and_date(monkeypatch):
    captured = {}

    class _ServiceStub:
        async def get_business_overview_kpi(
            self,
            month=None,
            platform=None,
            granularity="monthly",
            target_date=None,
            shop_id=None,
        ):
            captured.update(
                {
                    "month": month,
                    "platform": platform,
                    "granularity": granularity,
                    "target_date": target_date,
                }
            )
            return {"gmv": 456}

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )
    monkeypatch.setattr(
        "backend.domains.business.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_business_overview_kpi_postgresql(
            request=_make_request("/api/dashboard/business-overview/kpi"),
            granularity="weekly",
            period_key="2026-03-16",
            platform_code="shopee",
            shop_id=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert body["data"]["gmv"] == 456
    assert captured["month"] == "2026-03-16"
    assert captured["platform"] == "shopee"
    assert captured["granularity"] == "weekly"
    assert captured["target_date"] == "2026-03-16"


def test_postgresql_kpi_route_forwards_shop_id(monkeypatch):
    captured = {}

    class _ServiceStub:
        async def get_business_overview_kpi(
            self,
            month=None,
            platform=None,
            granularity="monthly",
            target_date=None,
            shop_id=None,
        ):
            captured.update(
                {
                    "month": month,
                    "platform": platform,
                    "granularity": granularity,
                    "target_date": target_date,
                    "shop_id": shop_id,
                }
            )
            return {"gmv": 456}

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )
    monkeypatch.setattr(
        "backend.domains.business.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_business_overview_kpi_postgresql(
            request=_make_request("/api/dashboard/business-overview/kpi"),
            granularity="monthly",
            period_key="2026-03-01",
            platform_code="shopee",
            shop_id="shop-1",
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert captured["platform"] == "shopee"
    assert captured["shop_id"] == "shop-1"


@pytest.mark.asyncio
async def test_postgresql_kpi_route_rejects_legacy_month_param(monkeypatch):
    def _service_should_not_be_called():
        raise AssertionError("Service should not be called when legacy params are provided")

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        _service_should_not_be_called,
    )

    app = FastAPI()
    app.state.dashboard_assets_report = {"ready": True}
    app.include_router(router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/dashboard/business-overview/kpi",
            params={"granularity": "monthly", "period_key": "2026-03-01", "month": "2026-03-01"},
        )

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 422
    assert body["detail"]["message"] == "Business Overview API no longer accepts legacy query params."
    assert "month" in body["detail"]["legacy_params"]


@pytest.mark.asyncio
async def test_dashboard_readiness_guard_refreshes_stale_app_state(monkeypatch):
    stale_report = {
        "ready": False,
        "assets_drift": True,
        "modules": {
            "business_overview": {
                "status": "drift",
                "ready": False,
                "assets_drift": True,
            }
        },
    }
    fresh_report = {
        "ready": True,
        "assets_drift": False,
        "modules": {
            "business_overview": {
                "status": "ready",
                "ready": True,
                "assets_drift": False,
            }
        },
    }
    app = SimpleNamespace(
        state=SimpleNamespace(
            dashboard_assets_ready=False,
            dashboard_assets_report=stale_report,
        )
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/dashboard/business-overview/kpi",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 8001),
            "app": app,
        }
    )

    class _FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(
        "backend.domains.business.routers.dashboard_api_postgresql.AsyncSessionLocal",
        lambda: _FakeSession(),
    )

    async def _fake_inspect(_session):
        return fresh_report

    monkeypatch.setattr(
        "backend.domains.business.routers.dashboard_api_postgresql.inspect_dashboard_assets",
        _fake_inspect,
    )

    await _require_dashboard_assets_ready(request)

    assert app.state.dashboard_assets_ready is True
    assert app.state.dashboard_assets_report == fresh_report


def test_postgresql_comparison_route_returns_service_payload(monkeypatch):
    class _ServiceStub:
        async def get_business_overview_comparison(self, granularity, target_date, platform):
            return {
                "metrics": {
                    "sales_amount": {"today": 100, "yesterday": 90, "average": 10, "change": 11.11}
                },
                "target": {"sales_amount": 120, "achievement_rate": 83.33},
            }

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_business_overview_comparison_postgresql(
            request=_make_request("/api/dashboard/business-overview/comparison"),
            granularity="monthly",
            period_key="2026-03-01",
            platform_code=None,
            shop_id=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert "metrics" in body["data"]


@pytest.mark.asyncio
async def test_postgresql_business_overview_bootstrap_runs_module_calls_concurrently(monkeypatch):
    active = 0
    max_active = 0

    async def tracked(value):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return value

    class _ServiceStub:
        async def get_business_overview_kpi(self, **_kwargs):
            return await tracked({"gmv": 100})

        async def get_business_overview_comparison(self, **_kwargs):
            return await tracked({"metrics": {}})

        async def get_business_overview_operational_metrics(self, **_kwargs):
            return await tracked({"monthly_target": 100, "meta": {}})

        async def get_business_overview_traffic_ranking(self, **_kwargs):
            return await tracked([{"name": "shop-a", "rank": 1}])

        async def get_business_overview_shop_racing(self, **_kwargs):
            return await tracked([{"name": "shop-a", "rank": 1}])

        async def get_business_overview_data_freshness(self, **_kwargs):
            return await tracked({"orders": {}, "traffic": {}, "is_stale": False, "warnings": []})

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )
    monkeypatch.setattr(
        "backend.domains.business.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = await get_business_overview_bootstrap_postgresql(
        request=_make_request("/api/dashboard/business-overview/bootstrap"),
        granularity="monthly",
        period_key="2026-03-01",
        platform_code=None,
        shop_id=None,
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert {
        "kpi",
        "comparison",
        "operational_metrics",
        "traffic_ranking",
        "shop_racing",
    }.issubset(set(body["data"]))
    assert body["data"]["meta"]["data_freshness"]["is_stale"] is False
    assert max_active > 1


@pytest.mark.asyncio
async def test_postgresql_business_overview_bootstrap_miss_reuses_module_caches(monkeypatch):
    cache_calls = []

    class _CacheServiceStub:
        async def get(self, cache_type, **kwargs):
            cache_calls.append(("get", cache_type, dict(kwargs)))
            return None

        async def get_or_set_singleflight(self, cache_type, producer, **kwargs):
            cache_calls.append(("get_or_set_singleflight", cache_type, dict(kwargs)))
            return await producer()

    class _ServiceStub:
        async def get_business_overview_kpi(self, **_kwargs):
            return {"gmv": 100}

        async def get_business_overview_comparison(self, **_kwargs):
            return {"metrics": {}}

        async def get_business_overview_operational_metrics(self, **_kwargs):
            return {"monthly_target": 100, "meta": {}}

        async def get_business_overview_traffic_ranking(self, **_kwargs):
            return []

        async def get_business_overview_shop_racing(self, **_kwargs):
            return []

        async def get_business_overview_data_freshness(self, **_kwargs):
            return {"orders": {}, "traffic": {}, "is_stale": False, "warnings": []}

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )
    monkeypatch.setattr(
        "backend.domains.business.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = await get_business_overview_bootstrap_postgresql(
        request=_make_cached_request(
            "/api/dashboard/business-overview/bootstrap",
            _CacheServiceStub(),
        ),
        granularity="monthly",
        period_key="2026-03-01",
        platform_code="shopee",
        shop_id=None,
    )

    singleflight_types = {
        cache_type
        for method, cache_type, _kwargs in cache_calls
        if method == "get_or_set_singleflight"
    }
    assert response.headers["X-Cache"] == "MISS"
    assert {
        "dashboard_business_overview_bootstrap",
        "dashboard_kpi",
        "dashboard_comparison",
        "dashboard_operational_metrics",
        "dashboard_traffic_ranking",
        "dashboard_shop_racing",
    }.issubset(singleflight_types)


def test_postgresql_shop_racing_route_returns_service_payload(monkeypatch):
    class _ServiceStub:
        async def get_business_overview_shop_racing(self, granularity, target_date, group_by, platform):
            return [{"name": "shop-a", "gmv": 100, "rank": 1}]

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_business_overview_shop_racing_postgresql(
            request=_make_request("/api/dashboard/business-overview/shop-racing"),
            granularity="monthly",
            period_key="2026-03-01",
            group_by="shop",
            platform_code="shopee",
            shop_id=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert body["data"][0]["rank"] == 1


def test_postgresql_traffic_ranking_route_returns_service_payload(monkeypatch):
    class _ServiceStub:
        async def get_business_overview_traffic_ranking(self, granularity, target_date, dimension, platform):
            return [{"name": "shop-a", "visitor_count": 100, "rank": 1}]

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_business_overview_traffic_ranking_postgresql(
            request=_make_request("/api/dashboard/business-overview/traffic-ranking"),
            granularity="monthly",
            dimension="visitor",
            period_key="2026-03-01",
            platform_code="shopee",
            shop_id=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert body["data"][0]["rank"] == 1


@pytest.mark.asyncio
async def test_postgresql_traffic_ranking_route_rejects_legacy_date_value_alias(monkeypatch):
    captured = {}

    class _ServiceStub:
        async def get_business_overview_traffic_ranking(self, granularity, target_date, dimension, platform):
            captured["granularity"] = granularity
            captured["target_date"] = target_date
            captured["dimension"] = dimension
            captured["platform"] = platform
            return [{"name": "shop-a", "visitor_count": 100, "rank": 1}]

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    app = FastAPI()
    app.state.dashboard_assets_report = {"ready": True}
    app.include_router(router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/dashboard/business-overview/traffic-ranking",
            params={
                "granularity": "monthly",
                "dimension": "shop",
                "period_key": "2026-03-01",
                "date_value": "2026-03-01",
            },
        )

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 422
    assert body["detail"]["message"] == "Business Overview API no longer accepts legacy query params."
    assert "date_value" in body["detail"]["legacy_params"]


def test_postgresql_operational_metrics_route_returns_service_payload(monkeypatch):
    class _ServiceStub:
        async def get_business_overview_operational_metrics(self, month, platform, shop_id=None):
            return {
                "monthly_target": 100,
                "monthly_total_achieved": 80,
                "estimated_expenses": 30,
                "operating_result_text": "盈利",
            }

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )
    monkeypatch.setattr(
        "backend.domains.business.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_business_overview_operational_metrics_postgresql(
            request=_make_request("/api/dashboard/business-overview/operational-metrics"),
            granularity="monthly",
            period_key="2026-03-01",
            platform_code=None,
            shop_id=None,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert body["data"]["operating_result_text"] == "盈利"


def test_postgresql_operational_metrics_route_forwards_shop_id(monkeypatch):
    captured = {}

    class _ServiceStub:
        async def get_business_overview_operational_metrics(self, month, platform, shop_id=None):
            captured.update({"month": month, "platform": platform, "shop_id": shop_id})
            return {
                "monthly_target": 100,
                "monthly_total_achieved": 80,
                "estimated_expenses": 30,
                "operating_result_text": "盈利",
            }

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )
    monkeypatch.setattr(
        "backend.domains.business.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_business_overview_operational_metrics_postgresql(
            request=_make_request("/api/dashboard/business-overview/operational-metrics"),
            granularity="monthly",
            period_key="2026-03-01",
            platform_code="shopee",
            shop_id="shop-1",
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert captured["platform"] == "shopee"
    assert captured["shop_id"] == "shop-1"


def test_postgresql_dashboard_router_exposes_compatibility_paths():
    paths = {route.path for route in router.routes}
    assert "/api/dashboard/business-overview/kpi" in paths
    assert "/api/dashboard/business-overview/comparison" in paths
    assert "/api/dashboard/business-overview/shop-racing" in paths
    assert "/api/dashboard/business-overview/traffic-ranking" in paths
    assert "/api/dashboard/business-overview/inventory-backlog" in paths
    assert "/api/dashboard/business-overview/operational-metrics" in paths
    assert "/api/dashboard/clearance-ranking" in paths


def test_postgresql_inventory_backlog_route_returns_summary_payload(monkeypatch):
    class _ServiceStub:
        async def get_business_overview_inventory_backlog(
            self,
            min_days,
            limit,
            granularity=None,
            target_date=None,
        ):
            return {
                "summary": {"total_value": 1000, "backlog_30d_value": 300},
                "top_products": [
                    {
                        "platform_code": "shopee",
                        "platform_sku": "SKU-1",
                        "estimated_turnover_days": 45,
                        "risk_level": "medium",
                        "clearance_priority_score": 123.4,
                    }
                ],
            }

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_business_overview_inventory_backlog_postgresql(
            request=_make_request("/api/dashboard/business-overview/inventory-backlog"),
            days=30,
            limit=20,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert body["data"]["summary"]["total_value"] == 1000
    assert body["data"]["top_products"][0]["risk_level"] == "medium"


def test_postgresql_inventory_backlog_route_forwards_limit(monkeypatch):
    captured = {}

    class _ServiceStub:
        async def get_business_overview_inventory_backlog(
            self,
            min_days,
            limit,
            granularity=None,
            target_date=None,
        ):
            captured["min_days"] = min_days
            captured["limit"] = limit
            captured["granularity"] = granularity
            captured["target_date"] = target_date
            return {"summary": {"total_value": 1000}, "top_products": []}

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_business_overview_inventory_backlog_postgresql(
            request=_make_request("/api/dashboard/business-overview/inventory-backlog"),
            days=30,
            limit=20,
            granularity="weekly",
            date="2026-03-16",
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert captured == {
        "min_days": 30,
        "limit": 20,
        "granularity": "weekly",
        "target_date": "2026-03-16",
    }


@pytest.mark.asyncio
async def test_postgresql_inventory_backlog_route_uses_extended_singleflight_timeouts(monkeypatch):
    cache_calls = []

    class _ServiceStub:
        async def get_business_overview_inventory_backlog(
            self,
            min_days,
            limit,
            granularity=None,
            target_date=None,
        ):
            return {"summary": {"total_value": 1000}, "top_products": []}

    class _CacheServiceStub:
        async def get(self, cache_type, **kwargs):
            cache_calls.append(("get", cache_type, dict(kwargs)))
            return None

        async def get_or_set_singleflight(self, cache_type, producer, **kwargs):
            cache_calls.append(("get_or_set_singleflight", cache_type, dict(kwargs)))
            return await producer()

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    app = FastAPI()
    app.state.dashboard_assets_report = {"ready": True}
    app.state.cache_service = _CacheServiceStub()
    app.include_router(router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/dashboard/business-overview/inventory-backlog",
            params={"days": 30, "limit": 20},
        )

    assert response.status_code == 200
    singleflight_call = next(call for call in cache_calls if call[0] == "get_or_set_singleflight")
    assert singleflight_call[1] == "dashboard_inventory_backlog"
    assert singleflight_call[2]["days"] == "30"
    assert singleflight_call[2]["limit"] == "20"
    assert singleflight_call[2]["lock_ttl"] >= 60
    assert singleflight_call[2]["wait_timeout"] >= 30


def test_postgresql_clearance_ranking_route_returns_priority_fields(monkeypatch):
    class _ServiceStub:
        async def get_clearance_ranking(
            self,
            limit,
            min_days=30,
            granularity=None,
            target_date=None,
        ):
            return [
                {
                    "platform_code": "shopee",
                    "platform_sku": "SKU-1",
                    "estimated_turnover_days": 80,
                    "estimated_stagnant_days": 14,
                    "stagnant_snapshot_count": 3,
                    "risk_level": "high",
                    "clearance_priority_score": 456.7,
                }
            ]

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_clearance_ranking_postgresql(
            request=_make_request("/api/dashboard/clearance-ranking"),
            limit=10,
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert body["data"][0]["risk_level"] == "high"
    assert body["data"][0]["clearance_priority_score"] == 456.7


def test_postgresql_clearance_ranking_route_forwards_granularity_and_date(monkeypatch):
    captured = {}

    class _ServiceStub:
        async def get_clearance_ranking(
            self,
            limit,
            min_days=30,
            granularity=None,
            target_date=None,
        ):
            captured["limit"] = limit
            captured["min_days"] = min_days
            captured["granularity"] = granularity
            captured["target_date"] = target_date
            return []

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    response = asyncio.run(
        get_clearance_ranking_postgresql(
            request=_make_request("/api/dashboard/clearance-ranking"),
            limit=10,
            granularity="monthly",
            date="2026-03-01",
        )
    )

    body = json.loads(response.body.decode("utf-8"))
    assert body["success"] is True
    assert captured == {
        "limit": 10,
        "min_days": 30,
        "granularity": "monthly",
        "target_date": "2026-03-01",
    }


@pytest.mark.parametrize(
    ("route_func", "kwargs"),
    [
        (
            get_business_overview_inventory_backlog_postgresql,
            {
                "request": _make_dashboard_not_ready_request("/api/dashboard/business-overview/inventory-backlog"),
                "days": 30,
                "limit": 20,
            },
        ),
        (
            get_business_overview_operational_metrics_postgresql,
            {
                "request": _make_dashboard_not_ready_request("/api/dashboard/business-overview/operational-metrics"),
                "granularity": "monthly",
                "period_key": "2026-03-01",
                "platform_code": None,
                "shop_id": None,
            },
        ),
        (
            get_clearance_ranking_postgresql,
            {
                "request": _make_dashboard_not_ready_request("/api/dashboard/clearance-ranking"),
                "limit": 10,
            },
        ),
    ],
)
def test_dashboard_routes_preserve_http_503_when_assets_not_ready(route_func, kwargs):
    try:
        response = asyncio.run(route_func(**kwargs))
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 503
    else:
        assert response.status_code == 503


def test_business_overview_schema_contract_accepts_bootstrap_payload():
    from backend.schemas.dashboard import BusinessOverviewBootstrapPayload

    payload = {
        "kpi": {"gmv": 100, "order_count": 10},
        "comparison": {
            "metrics": {
                "sales_amount": {
                    "today": 100,
                    "yesterday": 90,
                    "average": 95,
                    "change": 11.11,
                }
            },
            "target": {"sales_amount": 120, "achievement_rate": 83.33},
        },
        "operational_metrics": {
            "monthly_target": 120,
            "monthly_total_achieved": 100,
            "meta": {
                "profit_source": "orders_raw_profit_field",
                "target_source": "service_target_summary",
                "expenses_source": "shop_month_rows_sum",
                "warnings": [],
            },
        },
        "traffic_ranking": [
            {"name": "shop-a", "visitor_count": 100, "page_views": 200, "rank": 1}
        ],
        "shop_racing": [
            {"name": "shop-a", "gmv": 100, "target_amount": 120, "rank": 1}
        ],
    }

    model = BusinessOverviewBootstrapPayload.model_validate(payload)

    assert model.kpi.gmv == 100
    assert model.operational_metrics.meta["target_source"] == "service_target_summary"
