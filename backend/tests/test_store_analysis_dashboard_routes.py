import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.dependencies.auth import get_current_user
from backend.domains.business.routers.dashboard_api_postgresql import router


def _make_user(*roles, is_superuser=False):
    return SimpleNamespace(
        is_superuser=is_superuser,
        roles=[SimpleNamespace(role_code=role, role_name=role) for role in roles],
    )


def _build_app(role_codes=None):
    app = FastAPI()
    app.include_router(router)
    if role_codes is not None:
        app.dependency_overrides[get_current_user] = lambda: _make_user(*role_codes)
    return app


def test_store_analysis_routes_are_registered():
    paths = {route.path for route in router.routes}
    assert "/api/dashboard/store-analysis/capabilities" in paths
    assert "/api/dashboard/store-analysis/shops" in paths
    assert "/api/dashboard/store-analysis/overview" in paths
    assert "/api/dashboard/store-analysis/comparison" in paths
    assert "/api/dashboard/store-analysis/top-products" in paths
    assert "/api/dashboard/store-analysis/traffic-summary" in paths
    assert "/api/dashboard/store-analysis/traffic-trend" in paths


@pytest.mark.asyncio
async def test_store_analysis_traffic_trend_route_rejects_missing_params():
    app = _build_app(["operator"])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/dashboard/store-analysis/traffic-trend")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_store_analysis_capability_route_rejects_missing_platform_or_shop():
    app = _build_app(["operator"])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/dashboard/store-analysis/capabilities")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_store_analysis_shops_route_requires_platform():
    app = _build_app(["operator"])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/dashboard/store-analysis/shops")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_store_analysis_shops_route_returns_shop_options(monkeypatch):
    class _ServiceStub:
        async def get_store_analysis_shops(self, platform):
            return [
                {"shop_id": "1407964586", "platform_code": "shopee"},
                {"shop_id": "1227491331", "platform_code": "shopee"},
            ]

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    app = _build_app(["operator"])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/dashboard/store-analysis/shops",
            params={"platform": "shopee"},
        )

    assert response.status_code == 200
    body = json.loads(response.content.decode("utf-8"))
    assert body["success"] is True
    assert body["data"][0]["shop_id"] == "1407964586"


@pytest.mark.asyncio
async def test_store_analysis_overview_route_requires_platform_shop_granularity_and_date():
    app = _build_app(["operator"])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/dashboard/store-analysis/overview")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_store_analysis_overview_route_returns_overview_payload(monkeypatch):
    class _ServiceStub:
        async def get_store_analysis_overview(self, platform, shop_id, granularity, target_date):
            return {
                "platform_code": platform,
                "shop_id": shop_id,
                "requested_granularity": granularity,
                "gmv": 1234.5,
                "order_count": 12,
                "avg_order_value": 102.88,
                "achievement_rate": 88.8,
                "profit": 320.1,
                "monthly_target": 5000,
                "monthly_achievement_rate": 24.69,
                "time_gap": -12.5,
                "operating_result": 100.0,
                "operating_result_text": "盈利",
            }

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    app = _build_app(["operator"])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/dashboard/store-analysis/overview",
            params={
                "platform": "shopee",
                "shop_id": "1407964586",
                "granularity": "daily",
                "date": "2026-04-12",
            },
        )

    assert response.status_code == 200
    body = json.loads(response.content.decode("utf-8"))
    assert body["success"] is True
    assert body["data"]["gmv"] == 1234.5
    assert body["data"]["operating_result_text"] == "盈利"


@pytest.mark.asyncio
async def test_store_analysis_comparison_route_requires_platform_shop_granularity_and_date():
    app = _build_app(["operator"])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/dashboard/store-analysis/comparison")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_store_analysis_comparison_route_returns_payload(monkeypatch):
    class _ServiceStub:
        async def get_store_analysis_comparison(self, platform, shop_id, granularity, target_date):
            return {
                "requested_granularity": granularity,
                "current_period_label": "2026-04-12",
                "previous_period_label": "2026-04-11",
                "metrics": {
                    "gmv": {"current": 100, "previous": 80, "change_pct": 25.0},
                    "visitor_count": {"current": 50, "previous": 40, "change_pct": 25.0},
                },
            }

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    app = _build_app(["operator"])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/dashboard/store-analysis/comparison",
            params={
                "platform": "shopee",
                "shop_id": "1407964586",
                "granularity": "daily",
                "date": "2026-04-12",
            },
        )

    assert response.status_code == 200
    body = json.loads(response.content.decode("utf-8"))
    assert body["success"] is True
    assert body["data"]["metrics"]["gmv"]["current"] == 100
    assert body["data"]["current_period_label"] == "2026-04-12"


@pytest.mark.asyncio
async def test_store_analysis_top_products_route_requires_platform_shop_granularity_and_date():
    app = _build_app(["operator"])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/dashboard/store-analysis/top-products")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_store_analysis_top_products_route_returns_payload(monkeypatch):
    class _ServiceStub:
        async def get_store_analysis_top_products(self, platform, shop_id, granularity, target_date, limit=10):
            return [
                {"product_name": "Prod A", "sales_amount": 500, "order_count": 10, "sales_volume": 12},
                {"product_name": "Prod B", "sales_amount": 300, "order_count": 8, "sales_volume": 9},
            ]

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    app = _build_app(["operator"])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/dashboard/store-analysis/top-products",
            params={
                "platform": "shopee",
                "shop_id": "1407964586",
                "granularity": "daily",
                "date": "2026-04-12",
                "limit": 5,
            },
        )

    assert response.status_code == 200
    body = json.loads(response.content.decode("utf-8"))
    assert body["success"] is True
    assert body["data"][0]["product_name"] == "Prod A"


@pytest.mark.asyncio
async def test_store_analysis_daily_tiktok_does_not_return_hourly_effective_granularity(monkeypatch):
    class _ServiceStub:
        async def get_store_analysis_traffic_trend(self, platform, shop_id, granularity, target_date):
            return {
                "requested_granularity": granularity,
                "effective_granularity": "daily",
                "items": [],
            }

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    app = _build_app(["operator"])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/dashboard/store-analysis/traffic-trend",
            params={
                "platform": "tiktok",
                "shop_id": "shop-1",
                "granularity": "daily",
                "date": "2025-09-23",
            },
        )

    assert response.status_code == 200
    body = json.loads(response.content.decode("utf-8"))
    assert body["success"] is True
    assert body["data"]["effective_granularity"] == "daily"


@pytest.mark.asyncio
async def test_store_analysis_daily_shopee_returns_hourly_effective_granularity(monkeypatch):
    class _ServiceStub:
        async def get_store_analysis_traffic_trend(self, platform, shop_id, granularity, target_date):
            return {
                "requested_granularity": granularity,
                "effective_granularity": "hourly",
                "items": [],
            }

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    app = _build_app(["operator"])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/dashboard/store-analysis/traffic-trend",
            params={
                "platform": "shopee",
                "shop_id": "shop-1",
                "granularity": "daily",
                "date": "2025-09-23",
            },
        )

    assert response.status_code == 200
    body = json.loads(response.content.decode("utf-8"))
    assert body["success"] is True
    assert body["data"]["effective_granularity"] == "hourly"


@pytest.mark.asyncio
async def test_store_analysis_route_returns_401_when_unauthenticated():
    app = FastAPI()
    app.include_router(router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/dashboard/store-analysis/shops",
            params={"platform": "shopee"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_store_analysis_route_returns_403_when_role_not_allowed():
    app = _build_app(["finance"])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/dashboard/store-analysis/shops",
            params={"platform": "shopee"},
        )

    assert response.status_code == 403
