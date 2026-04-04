import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.dependencies.auth import get_current_user
from backend.routers.dashboard_api_postgresql import router
from backend.services.postgresql_dashboard_service import PostgresqlDashboardService


def _make_user(role_code: str = "admin") -> SimpleNamespace:
    return SimpleNamespace(
        is_superuser=False,
        roles=[SimpleNamespace(role_code=role_code, role_name=role_code)],
    )


def _build_app_with_auth_override(user: SimpleNamespace | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    if user is not None:
        async def _override_current_user():
            return user

        app.dependency_overrides[get_current_user] = _override_current_user

    return app


def test_postgresql_b_cost_routes_are_registered():
    paths = {route.path for route in router.routes}
    assert "/api/dashboard/b-cost-analysis/overview" in paths
    assert "/api/dashboard/b-cost-analysis/shop-month" in paths
    assert "/api/dashboard/b-cost-analysis/order-detail" in paths


@pytest.mark.asyncio
async def test_postgresql_b_cost_overview_route_returns_service_payload_and_passes_filters(monkeypatch):
    captured = {}

    class _ServiceStub:
        async def get_b_cost_analysis_overview(self, period_month, platform=None, shop_id=None):
            captured["period_month"] = period_month
            captured["platform"] = platform
            captured["shop_id"] = shop_id
            return {"summary": "ok", "period_month": "2026-03-01"}

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    app = _build_app_with_auth_override(_make_user("admin"))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/dashboard/b-cost-analysis/overview",
            params={
                "period_month": "2026-03",
                "platform": "shopee",
                "shop_id": "shop-1",
            },
        )

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["summary"] == "ok"
    assert captured == {
        "period_month": "2026-03",
        "platform": "shopee",
        "shop_id": "shop-1",
    }


@pytest.mark.asyncio
async def test_postgresql_b_cost_shop_month_route_returns_service_payload_and_passes_filters(monkeypatch):
    captured = {}

    class _ServiceStub:
        async def get_b_cost_analysis_shop_month(self, period_month, platform=None, shop_id=None):
            captured["period_month"] = period_month
            captured["platform"] = platform
            captured["shop_id"] = shop_id
            return [{"shop_id": "shop-1", "gmv": 100}]

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    app = _build_app_with_auth_override(_make_user("manager"))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/dashboard/b-cost-analysis/shop-month",
            params={
                "period_month": "2026-03-01",
                "platform": "tiktok",
                "shop_id": "shop-2",
            },
        )

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"][0]["shop_id"] == "shop-1"
    assert captured == {
        "period_month": "2026-03-01",
        "platform": "tiktok",
        "shop_id": "shop-2",
    }


@pytest.mark.asyncio
async def test_postgresql_b_cost_order_detail_route_returns_paginated_payload_and_passes_pagination(monkeypatch):
    captured = {}

    class _ServiceStub:
        async def get_b_cost_analysis_order_detail(
            self,
            period_month,
            platform=None,
            shop_id=None,
            page=1,
            page_size=20,
        ):
            captured["period_month"] = period_month
            captured["platform"] = platform
            captured["shop_id"] = shop_id
            captured["page"] = page
            captured["page_size"] = page_size
            return {
                "items": [{"order_id": "ORD-1"}],
                "page": page,
                "page_size": page_size,
                "total": 1,
            }

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    app = _build_app_with_auth_override(_make_user("finance"))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/dashboard/b-cost-analysis/order-detail",
            params={
                "period_month": "2026-03-01",
                "platform": "shopee",
                "shop_id": "shop-9",
                "page": 3,
                "page_size": 50,
            },
        )

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["items"][0]["order_id"] == "ORD-1"
    assert body["data"]["page"] == 3
    assert body["data"]["page_size"] == 50
    assert body["data"]["total"] == 1
    assert captured == {
        "period_month": "2026-03-01",
        "platform": "shopee",
        "shop_id": "shop-9",
        "page": 3,
        "page_size": 50,
    }


@pytest.mark.asyncio
async def test_postgresql_b_cost_overview_route_requires_period_month():
    app = _build_app_with_auth_override(_make_user("admin"))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/dashboard/b-cost-analysis/overview")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_postgresql_b_cost_shop_month_route_requires_period_month():
    app = _build_app_with_auth_override(_make_user("admin"))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/dashboard/b-cost-analysis/shop-month")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_postgresql_b_cost_order_detail_route_requires_period_month():
    app = _build_app_with_auth_override(_make_user("admin"))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/dashboard/b-cost-analysis/order-detail")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_postgresql_b_cost_order_detail_route_maps_value_error_to_400():
    app = _build_app_with_auth_override(_make_user("admin"))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/dashboard/b-cost-analysis/order-detail",
            params={"period_month": "2026-03-01", "page": 0, "page_size": 20},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_postgresql_b_cost_service_order_detail_normalizes_period_month_to_month_start(monkeypatch):
    service = PostgresqlDashboardService()
    calls = []

    async def fake_fetch_rows(query, params):
        calls.append((query, dict(params)))
        if "COUNT(1) AS total" in query:
            return [{"total": 1}]
        return [{"order_id": "ORD-1"}]

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)

    payload = await service.get_b_cost_analysis_order_detail(
        period_month="2026-03-15",
        platform="shopee",
        shop_id="shop-1",
        page=2,
        page_size=10,
    )

    assert payload["page"] == 2
    assert payload["page_size"] == 10
    assert payload["total"] == 1
    assert len(calls) == 2
    assert calls[0][1]["period_month"].isoformat() == "2026-03-01"
    assert calls[1][1]["period_month"].isoformat() == "2026-03-01"
    assert calls[1][1]["offset"] == 10
    assert calls[1][1]["limit"] == 10


@pytest.mark.asyncio
async def test_postgresql_b_cost_service_overview_normalizes_period_month_to_month_start(monkeypatch):
    service = PostgresqlDashboardService()
    calls = []

    async def fake_fetch_rows(query, params):
        calls.append((query, dict(params)))
        return []

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)

    await service.get_b_cost_analysis_overview(
        period_month="2026-03-15",
        platform="shopee",
        shop_id=None,
    )

    assert len(calls) == 1
    assert calls[0][1]["period_month"].isoformat() == "2026-03-01"


@pytest.mark.asyncio
async def test_postgresql_b_cost_service_shop_month_normalizes_period_month_to_month_start(monkeypatch):
    service = PostgresqlDashboardService()
    calls = []

    async def fake_fetch_rows(query, params):
        calls.append((query, dict(params)))
        return []

    monkeypatch.setattr(service, "_fetch_rows", fake_fetch_rows)

    await service.get_b_cost_analysis_shop_month(
        period_month="2026-03-15",
        platform="shopee",
        shop_id="shop-1",
    )

    assert len(calls) == 1
    assert calls[0][1]["period_month"].isoformat() == "2026-03-01"


@pytest.mark.asyncio
async def test_postgresql_b_cost_overview_route_normalizes_period_month_for_cache(monkeypatch):
    cache_calls = []

    class _ServiceStub:
        async def get_b_cost_analysis_overview(self, period_month, platform=None, shop_id=None):
            return {"ok": True}

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
    app.state.cache_service = _CacheServiceStub()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _make_user("admin")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp_a = await client.get(
            "/api/dashboard/b-cost-analysis/overview",
            params={"period_month": "2026-03", "platform": "shopee"},
        )
        resp_b = await client.get(
            "/api/dashboard/b-cost-analysis/overview",
            params={"period_month": "2026-03-15", "platform": "shopee"},
        )

    assert resp_a.status_code == 200
    assert resp_b.status_code == 200
    assert cache_calls[0][1] == "b_cost_analysis_overview"
    assert cache_calls[2][1] == "b_cost_analysis_overview"
    assert cache_calls[0][2]["period_month"] == cache_calls[2][2]["period_month"]


@pytest.mark.asyncio
async def test_postgresql_b_cost_overview_route_returns_401_when_unauthenticated():
    app = FastAPI()
    app.include_router(router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/dashboard/b-cost-analysis/overview",
            params={"period_month": "2026-03"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_postgresql_b_cost_overview_route_returns_403_when_role_not_allowed():
    app = _build_app_with_auth_override(_make_user("operator"))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/dashboard/b-cost-analysis/overview",
            params={"period_month": "2026-03"},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_postgresql_b_cost_overview_route_allows_finance_role(monkeypatch):
    class _ServiceStub:
        async def get_b_cost_analysis_overview(self, period_month, platform=None, shop_id=None):
            return {"summary": "ok"}

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    app = _build_app_with_auth_override(_make_user("finance"))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/dashboard/b-cost-analysis/overview",
            params={"period_month": "2026-03"},
        )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_postgresql_b_cost_overview_route_masks_internal_exception_message(monkeypatch):
    class _ServiceStub:
        async def get_b_cost_analysis_overview(self, period_month, platform=None, shop_id=None):
            raise RuntimeError("db exploded: super-secret")

    monkeypatch.setattr(
        "backend.routers.dashboard_api_postgresql.get_postgresql_dashboard_service",
        lambda: _ServiceStub(),
    )

    app = _build_app_with_auth_override(_make_user("admin"))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/dashboard/b-cost-analysis/overview",
            params={"period_month": "2026-03"},
        )

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 500
    assert body["message"] == "查询失败"
    assert "db exploded: super-secret" not in response.text
