import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.dependencies.auth import get_current_user
from backend.models.database import get_async_db


def _make_user(role_code: str = "finance") -> SimpleNamespace:
    return SimpleNamespace(
        is_superuser=False,
        roles=[SimpleNamespace(role_code=role_code, role_name=role_code)],
    )


@pytest.mark.asyncio
async def test_profit_basis_routes_return_service_payload(monkeypatch):
    from backend.routers import profit_basis as profit_basis_router

    class _ServiceStub:
        async def build_profit_basis(self, year_month, platform_code, shop_id, basis_version="A_ONLY_V1"):
            return {
                "period_month": year_month,
                "platform_code": platform_code,
                "shop_id": shop_id,
                "orders_profit_amount": 4000,
                "a_class_cost_amount": 1500,
                "b_class_cost_amount": 0,
                "profit_basis_amount": 2500,
                "basis_version": basis_version,
            }

    async def _override_db():
        yield object()

    app = FastAPI()
    app.include_router(profit_basis_router.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user("finance")
    app.dependency_overrides[get_async_db] = _override_db
    monkeypatch.setattr(
        "backend.routers.profit_basis.ProfitBasisService",
        lambda db: _ServiceStub(),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get(
            "/api/finance/profit-basis",
            params={"period_month": "2026-03", "platform_code": "shopee", "shop_id": "shop-1"},
        )

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["profit_basis_amount"] == 2500


@pytest.mark.asyncio
async def test_profit_basis_routes_require_finance_role():
    from backend.routers import profit_basis as profit_basis_router

    async def _override_db():
        yield object()

    app = FastAPI()
    app.include_router(profit_basis_router.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user("operator")
    app.dependency_overrides[get_async_db] = _override_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get(
            "/api/finance/profit-basis",
            params={"period_month": "2026-03", "platform_code": "shopee", "shop_id": "shop-1"},
        )

    assert response.status_code == 403
