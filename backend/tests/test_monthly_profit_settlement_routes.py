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
    module = _load_router_module()

    class _ServiceStub:
        async def get_month(self, period_month):
            return {
                "summary": {
                    "id": 11,
                    "period_month": period_month,
                    "net_profit_amount": 100000.0,
                    "personnel_actual_amount": 32000.0,
                    "follow_actual_amount": 18000.0,
                    "company_actual_amount": 50000.0,
                    "status": "draft",
                },
                "personnel_details": [],
                "follow_details": [],
                "adjustments": [],
            }

    async def _override_db():
        yield object()

    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user("finance")
    app.dependency_overrides[get_async_db] = _override_db
    monkeypatch.setattr(module, "MonthlyProfitSettlementService", lambda db: _ServiceStub())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get(
            "/api/finance/monthly-profit-settlement",
            params={"period_month": "2026-04"},
        )

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["summary"]["net_profit_amount"] == 100000.0


@pytest.mark.asyncio
async def test_rebuild_monthly_profit_settlement_route_returns_service_payload(monkeypatch):
    module = _load_router_module()
    submit_mock = AsyncMock()

    class _ServiceStub:
        async def rebuild_month(
            self,
            period_month,
            personnel_target_ratio,
            follow_target_ratio,
            company_target_ratio,
            adjustment_amount,
            adjustment_reason=None,
        ):
            return {
                "summary": {
                    "id": 12,
                    "period_month": period_month,
                    "personnel_target_ratio": personnel_target_ratio,
                    "follow_target_ratio": follow_target_ratio,
                    "company_target_ratio": company_target_ratio,
                    "adjustment_amount": adjustment_amount,
                },
                "personnel_details": [],
                "follow_details": [],
                "adjustments": [],
            }

    db_token = object()

    async def _override_db():
        yield db_token

    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user("finance")
    app.dependency_overrides[get_async_db] = _override_db
    monkeypatch.setattr(module, "MonthlyProfitSettlementService", lambda db: _ServiceStub())
    monkeypatch.setattr(
        "backend.services.approval_center_service.submit_monthly_profit_settlement_approval",
        submit_mock,
    )

    payload = {
        "period_month": "2026-04",
        "personnel_target_ratio": 0.3,
        "follow_target_ratio": 0.2,
        "company_target_ratio": 0.5,
        "adjustment_amount": 0.0,
        "adjustment_reason": "finance note",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/api/finance/monthly-profit-settlement/rebuild", json=payload)

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["summary"]["personnel_target_ratio"] == pytest.approx(0.3)
    submit_mock.assert_awaited_once()
    assert submit_mock.await_args.kwargs == {
        "db": db_token,
        "applicant_user_id": 1,
        "settlement_id": 12,
        "period_month": "2026-04",
    }


@pytest.mark.asyncio
async def test_rebuild_monthly_profit_settlement_route_returns_409_for_approved_month(monkeypatch):
    module = _load_router_module()

    class _ServiceStub:
        async def rebuild_month(
            self,
            period_month,
            personnel_target_ratio,
            follow_target_ratio,
            company_target_ratio,
            adjustment_amount,
            adjustment_reason=None,
        ):
            raise module.MonthlyProfitSettlementConflictError("settlement already approved; reopen before rebuild")

    async def _override_db():
        yield object()

    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user("finance")
    app.dependency_overrides[get_async_db] = _override_db
    monkeypatch.setattr(module, "MonthlyProfitSettlementService", lambda db: _ServiceStub())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/api/finance/monthly-profit-settlement/rebuild",
            json={
                "period_month": "2026-04",
                "personnel_target_ratio": 0.3,
                "follow_target_ratio": 0.2,
                "company_target_ratio": 0.5,
                "adjustment_amount": 0.0,
                "adjustment_reason": "finance note",
            },
        )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_update_monthly_profit_settlement_targets_route_returns_service_payload(monkeypatch):
    module = _load_router_module()

    class _ServiceStub:
        async def update_targets(self, settlement_id, body):
            return {
                "summary": {
                    "id": settlement_id,
                    "period_month": "2026-04",
                    **body,
                },
                "personnel_details": [],
                "follow_details": [],
                "adjustments": [],
            }

    async def _override_db():
        yield object()

    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user("finance")
    app.dependency_overrides[get_async_db] = _override_db
    monkeypatch.setattr(module, "MonthlyProfitSettlementService", lambda db: _ServiceStub())

    payload = {
        "personnel_target_ratio": 0.25,
        "follow_target_ratio": 0.15,
        "company_target_ratio": 0.6,
        "adjustment_amount": 2000.0,
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.put("/api/finance/monthly-profit-settlement/12/targets", json=payload)

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["summary"]["company_target_ratio"] == pytest.approx(0.6)


@pytest.mark.asyncio
async def test_approve_monthly_profit_settlement_route_returns_service_payload(monkeypatch):
    module = _load_router_module()
    sync_mock = AsyncMock()

    class _ServiceStub:
        async def approve(self, settlement_id, approver):
            return {
                "id": settlement_id,
                "status": "approved",
                "approved_by": approver,
            }

    db_token = object()

    async def _override_db():
        yield db_token

    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user("finance", user_id=9)
    app.dependency_overrides[get_async_db] = _override_db
    monkeypatch.setattr(module, "MonthlyProfitSettlementService", lambda db: _ServiceStub())
    monkeypatch.setattr(
        "backend.services.approval_center_service.sync_monthly_profit_settlement_approval_decision",
        sync_mock,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/api/finance/monthly-profit-settlement/12/approve")

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["status"] == "approved"
    assert body["data"]["approved_by"] == "9"
    sync_mock.assert_awaited_once()
    assert sync_mock.await_args.kwargs == {
        "db": db_token,
        "settlement_id": 12,
        "actor_user_id": 9,
        "action": "approve",
        "comment": "monthly_profit_settlement approved",
    }


@pytest.mark.asyncio
async def test_reopen_monthly_profit_settlement_route_returns_service_payload(monkeypatch):
    module = _load_router_module()

    class _ServiceStub:
        async def reopen(self, settlement_id):
            return {"id": settlement_id, "status": "draft"}

    async def _override_db():
        yield object()

    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user("finance", user_id=9)
    app.dependency_overrides[get_async_db] = _override_db
    monkeypatch.setattr(module, "MonthlyProfitSettlementService", lambda db: _ServiceStub())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/api/finance/monthly-profit-settlement/12/reopen")

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["status"] == "draft"


@pytest.mark.asyncio
async def test_update_monthly_profit_settlement_targets_route_returns_404_when_missing(monkeypatch):
    module = _load_router_module()

    class _ServiceStub:
        async def update_targets(self, settlement_id, body):
            raise LookupError("settlement not found")

    async def _override_db():
        yield object()

    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user("finance")
    app.dependency_overrides[get_async_db] = _override_db
    monkeypatch.setattr(module, "MonthlyProfitSettlementService", lambda db: _ServiceStub())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.put(
            "/api/finance/monthly-profit-settlement/999/targets",
            json={
                "personnel_target_ratio": 0.25,
                "follow_target_ratio": 0.15,
                "company_target_ratio": 0.6,
                "adjustment_amount": 0,
                "adjustment_reason": "finance note",
            },
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_approve_monthly_profit_settlement_route_returns_409_for_duplicate_approval(monkeypatch):
    module = _load_router_module()

    class _ServiceStub:
        async def approve(self, settlement_id, approver):
            raise ValueError("settlement already approved")

    async def _override_db():
        yield object()

    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user("finance", user_id=9)
    app.dependency_overrides[get_async_db] = _override_db
    monkeypatch.setattr(module, "MonthlyProfitSettlementService", lambda db: _ServiceStub())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/api/finance/monthly-profit-settlement/12/approve")

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_reopen_monthly_profit_settlement_route_returns_409_for_draft_settlement(monkeypatch):
    module = _load_router_module()

    class _ServiceStub:
        async def reopen(self, settlement_id):
            raise ValueError("only approved settlement can be reopened")

    async def _override_db():
        yield object()

    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user("finance", user_id=9)
    app.dependency_overrides[get_async_db] = _override_db
    monkeypatch.setattr(module, "MonthlyProfitSettlementService", lambda db: _ServiceStub())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/api/finance/monthly-profit-settlement/12/reopen")

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_approve_monthly_profit_settlement_route_returns_409_when_difference_threshold_exceeded(monkeypatch):
    module = _load_router_module()

    class _ServiceStub:
        async def approve(self, settlement_id, approver):
            raise ValueError("difference threshold exceeded")

    async def _override_db():
        yield object()

    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user("finance", user_id=9)
    app.dependency_overrides[get_async_db] = _override_db
    monkeypatch.setattr(module, "MonthlyProfitSettlementService", lambda db: _ServiceStub())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/api/finance/monthly-profit-settlement/12/approve")

    assert response.status_code == 409
