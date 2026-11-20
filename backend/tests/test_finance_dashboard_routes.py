from importlib import import_module
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.dependencies.auth import get_current_user
from backend.models.database import get_async_db


def _router_module():
    return import_module("backend.domains.business.routers.monthly_profit_settlement")


def test_adjustment_endpoints_exist():
    module = _router_module()
    paths = {route.path for route in module.router.routes}
    assert "/api/finance/monthly-profit-settlement/adjustments" in paths


def test_approval_endpoints_are_removed():
    module = _router_module()
    paths = {route.path for route in module.router.routes}
    for banned in (
        "/api/finance/monthly-profit-settlement/rebuild",
        "/api/finance/monthly-profit-settlement/{settlement_id}/targets",
        "/api/finance/monthly-profit-settlement/{settlement_id}/approve",
        "/api/finance/monthly-profit-settlement/{settlement_id}/reopen",
    ):
        assert banned not in paths, f"{banned} 必须随审批制下线"


def _make_user(role_code: str = "finance", user_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=user_id,
        is_superuser=False,
        roles=[SimpleNamespace(role_code=role_code, role_name=role_code)],
    )


def _build_app(module, service_stub):
    async def _override_db():
        yield object()

    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user("finance")
    app.dependency_overrides[get_async_db] = _override_db
    module.MonthlyProfitSettlementService = lambda db: service_stub
    return app


@pytest.mark.asyncio
async def test_create_adjustment_returns_service_payload(monkeypatch):
    module = _router_module()

    class _ServiceStub:
        async def add_adjustment(self, **kwargs):
            return {
                "id": 7,
                "period_month": kwargs["period_month"],
                "settlement_id": 3,
                "adjustment_type": kwargs["adjustment_type"],
                "amount": kwargs["amount"],
                "reason": kwargs["reason"],
                "created_by": kwargs["created_by"],
            }

    app = _build_app(module, _ServiceStub())
    monkeypatch.setattr(
        module, "MonthlyProfitSettlementService", lambda db: _ServiceStub()
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/finance/monthly-profit-settlement/adjustments",
            json={
                "period_month": "2026-04",
                "adjustment_type": "manual_adjustment",
                "amount": 1200.0,
                "reason": "finance note",
            },
        )

    body = response.json()
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["amount"] == 1200.0
    assert body["data"]["reason"] == "finance note"


@pytest.mark.asyncio
async def test_create_adjustment_rejects_blank_reason(monkeypatch):
    module = _router_module()

    class _ServiceStub:
        async def add_adjustment(self, **kwargs):
            raise module.MonthlyProfitSettlementValidationError(
                "adjustment reason is required"
            )

    app = _build_app(module, _ServiceStub())
    monkeypatch.setattr(
        module, "MonthlyProfitSettlementService", lambda db: _ServiceStub()
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/finance/monthly-profit-settlement/adjustments",
            json={
                "period_month": "2026-04",
                "adjustment_type": "manual_adjustment",
                "amount": 1200.0,
                "reason": "   ",
            },
        )

    assert response.status_code == 400
