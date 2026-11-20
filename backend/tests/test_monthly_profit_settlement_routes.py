import json
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.dependencies.auth import get_current_user
from backend.models.database import get_async_db


def _make_user(role_code: str = "finance", user_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=user_id,
        is_superuser=False,
        roles=[SimpleNamespace(role_code=role_code, role_name=role_code)],
    )


def _load_router_module():
    try:
        return import_module("backend.routers.monthly_profit_settlement")
    except ModuleNotFoundError as exc:
        pytest.fail(f"monthly profit settlement router module missing: {exc}")


@pytest.mark.asyncio
async def test_get_monthly_profit_settlement_route_returns_service_payload(monkeypatch):
    """GET 现在返回**扁平看板 payload**（旧信封 summary/personnel_details 已下线）。"""
    module = _load_router_module()

    class _ServiceStub:
        async def get_dashboard(self, period_month):
            return {
                "period_month": period_month,
                "as_of": "2026-04-30T00:00:00+00:00",
                "net_profit_amount": 100000.0,
                "performance_salary_amount": 10000.0,
                "commission_amount": 22000.0,
                "employee_allocation_amount": 32000.0,
                "manual_adjustment_amount": 0.0,
                "manual_adjustment_count": 0,
                "company_retained_amount": 68000.0,
                "allocation_ratio": 0.32,
                "over_allocation_flag": False,
                "shop_breakdown": [],
                "adjustments": [],
            }

    async def _override_db():
        yield object()

    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user("finance")
    app.dependency_overrides[get_async_db] = _override_db
    monkeypatch.setattr(module.domain_module, "MonthlyProfitSettlementService", lambda db: _ServiceStub())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get(
            "/api/finance/monthly-profit-settlement",
            params={"period_month": "2026-04"},
        )

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert body["success"] is True
    data = body["data"]
    assert data["period_month"] == "2026-04"
    assert "company_retained_amount" in data
    assert "shop_breakdown" in data
    assert data["net_profit_amount"] == 100000.0
