import json

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.routers.dashboard_api_postgresql import router


def test_store_analysis_routes_are_registered():
    paths = {route.path for route in router.routes}
    assert "/api/dashboard/store-analysis/capabilities" in paths
    assert "/api/dashboard/store-analysis/traffic-summary" in paths
    assert "/api/dashboard/store-analysis/traffic-trend" in paths


@pytest.mark.asyncio
async def test_store_analysis_traffic_trend_route_rejects_missing_params():
    app = FastAPI()
    app.include_router(router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/dashboard/store-analysis/traffic-trend")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_store_analysis_capability_route_rejects_missing_platform_or_shop():
    app = FastAPI()
    app.include_router(router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/dashboard/store-analysis/capabilities")

    assert response.status_code == 422


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

    app = FastAPI()
    app.include_router(router)

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

    app = FastAPI()
    app.include_router(router)

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
