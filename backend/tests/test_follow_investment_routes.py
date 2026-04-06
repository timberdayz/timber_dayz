import json
from types import SimpleNamespace

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


@pytest.mark.asyncio
async def test_follow_investment_settlement_calculate_route_returns_service_payload(monkeypatch):
    from backend.routers import follow_investment as follow_investment_router

    class _ServiceStub:
        async def calculate_settlement(self, year_month, platform_code, shop_id, distribution_ratio):
            return {
                "settlement": {
                    "period_month": year_month,
                    "platform_code": platform_code,
                    "shop_id": shop_id,
                    "distribution_ratio": distribution_ratio,
                    "profit_basis_amount": 80000,
                    "distributable_amount": 32000,
                },
                "details": [
                    {"investor_user_id": 101, "estimated_income": 24432},
                    {"investor_user_id": 102, "estimated_income": 7568},
                ],
            }

    async def _override_db():
        yield object()

    app = FastAPI()
    app.include_router(follow_investment_router.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user("finance")
    app.dependency_overrides[get_async_db] = _override_db
    monkeypatch.setattr(
        "backend.routers.follow_investment.FollowInvestmentService",
        lambda db: _ServiceStub(),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/api/finance/follow-investments/settlements/calculate",
            json={
                "period_month": "2026-03",
                "platform_code": "shopee",
                "shop_id": "shop-1",
                "distribution_ratio": 0.4,
            },
        )

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["settlement"]["distributable_amount"] == 32000
    assert len(body["data"]["details"]) == 2


@pytest.mark.asyncio
async def test_follow_investment_list_route_returns_service_payload(monkeypatch):
    from backend.routers import follow_investment as follow_investment_router

    class _ServiceStub:
        async def list_investments(self, platform_code=None, shop_id=None, status=None):
            return [
                {
                    "id": 1,
                    "investor_user_id": 101,
                    "platform_code": "shopee",
                    "shop_id": "shop-1",
                    "contribution_amount": 50000,
                    "status": "active",
                }
            ]

    async def _override_db():
        yield object()

    app = FastAPI()
    app.include_router(follow_investment_router.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user("finance")
    app.dependency_overrides[get_async_db] = _override_db
    monkeypatch.setattr(
        "backend.routers.follow_investment.FollowInvestmentService",
        lambda db: _ServiceStub(),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get(
            "/api/finance/follow-investments",
            params={"platform_code": "shopee", "shop_id": "shop-1"},
        )

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"][0]["contribution_amount"] == 50000


@pytest.mark.asyncio
async def test_follow_investment_create_route_returns_service_payload(monkeypatch):
    from backend.routers import follow_investment as follow_investment_router

    class _ServiceStub:
        async def create_investment(self, payload):
            return {
                "id": 2,
                "investor_user_id": payload["investor_user_id"],
                "platform_code": payload["platform_code"],
                "shop_id": payload["shop_id"],
                "contribution_amount": payload["contribution_amount"],
                "status": "active",
            }

    async def _override_db():
        yield object()

    app = FastAPI()
    app.include_router(follow_investment_router.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user("finance")
    app.dependency_overrides[get_async_db] = _override_db
    monkeypatch.setattr(
        "backend.routers.follow_investment.FollowInvestmentService",
        lambda db: _ServiceStub(),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/api/finance/follow-investments",
            json={
                "investor_user_id": 101,
                "platform_code": "shopee",
                "shop_id": "shop-1",
                "contribution_amount": 50000,
                "contribution_date": "2026-03-01",
                "remark": "seed",
            },
        )

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["status"] == "active"


@pytest.mark.asyncio
async def test_follow_investment_approve_route_returns_service_payload(monkeypatch):
    from backend.routers import follow_investment as follow_investment_router

    class _ServiceStub:
        async def approve_settlement(self, settlement_id, approver):
            return {
                "id": settlement_id,
                "status": "approved",
                "approved_by": approver,
            }

    async def _override_db():
        yield object()

    app = FastAPI()
    app.include_router(follow_investment_router.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user("finance", user_id=9)
    app.dependency_overrides[get_async_db] = _override_db
    monkeypatch.setattr(
        "backend.routers.follow_investment.FollowInvestmentService",
        lambda db: _ServiceStub(),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/api/finance/follow-investments/settlements/12/approve")

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["status"] == "approved"


@pytest.mark.asyncio
async def test_follow_investment_reopen_route_returns_service_payload(monkeypatch):
    from backend.routers import follow_investment as follow_investment_router

    class _ServiceStub:
        async def reopen_settlement(self, settlement_id):
            return {
                "id": settlement_id,
                "status": "draft",
            }

    async def _override_db():
        yield object()

    app = FastAPI()
    app.include_router(follow_investment_router.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user("finance", user_id=9)
    app.dependency_overrides[get_async_db] = _override_db
    monkeypatch.setattr(
        "backend.routers.follow_investment.FollowInvestmentService",
        lambda db: _ServiceStub(),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/api/finance/follow-investments/settlements/12/reopen")

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["status"] == "draft"


@pytest.mark.asyncio
async def test_follow_investment_settlements_list_route_returns_service_payload(monkeypatch):
    from backend.routers import follow_investment as follow_investment_router

    class _ServiceStub:
        async def list_settlements(self, period_month=None, platform_code=None, shop_id=None, status=None):
            return [
                {
                    "id": 12,
                    "period_month": "2026-03",
                    "platform_code": "shopee",
                    "shop_id": "shop-1",
                    "profit_basis_amount": 80000,
                    "distribution_ratio": 0.4,
                    "distributable_amount": 32000,
                    "status": "approved",
                }
            ]

    async def _override_db():
        yield object()

    app = FastAPI()
    app.include_router(follow_investment_router.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user("finance")
    app.dependency_overrides[get_async_db] = _override_db
    monkeypatch.setattr(
        "backend.routers.follow_investment.FollowInvestmentService",
        lambda db: _ServiceStub(),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get(
            "/api/finance/follow-investments/settlements",
            params={"period_month": "2026-03", "platform_code": "shopee", "shop_id": "shop-1"},
        )

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"][0]["status"] == "approved"


@pytest.mark.asyncio
async def test_follow_investment_settlement_calculate_route_requires_finance_role():
    from backend.routers import follow_investment as follow_investment_router

    async def _override_db():
        yield object()

    app = FastAPI()
    app.include_router(follow_investment_router.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user("operator")
    app.dependency_overrides[get_async_db] = _override_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/api/finance/follow-investments/settlements/calculate",
            json={
                "period_month": "2026-03",
                "platform_code": "shopee",
                "shop_id": "shop-1",
                "distribution_ratio": 0.4,
            },
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_follow_investment_create_route_requires_finance_role():
    from backend.routers import follow_investment as follow_investment_router

    async def _override_db():
        yield object()

    app = FastAPI()
    app.include_router(follow_investment_router.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user("operator")
    app.dependency_overrides[get_async_db] = _override_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/api/finance/follow-investments",
            json={
                "investor_user_id": 101,
                "platform_code": "shopee",
                "shop_id": "shop-1",
                "contribution_amount": 50000,
                "contribution_date": "2026-03-01",
            },
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_follow_investment_my_income_route_returns_current_user_payload(monkeypatch):
    from backend.routers import follow_investment as follow_investment_router

    class _ServiceStub:
        async def get_my_income(self, user_id, period_month=None):
            return {
                "summary": {
                    "estimated_income": 24432,
                    "approved_income": 24432,
                    "paid_income": 18000,
                    "current_contribution_amount": 50000,
                },
                "items": [
                    {
                        "period_month": "2026-03",
                        "platform_code": "shopee",
                        "shop_id": "shop-1",
                        "profit_basis_amount": 80000,
                        "share_ratio": 0.7635,
                        "estimated_income": 24432,
                        "approved_income": 24432,
                        "paid_income": 18000,
                        "status": "approved",
                    }
                ],
            }

    async def _override_db():
        yield object()

    app = FastAPI()
    app.include_router(follow_investment_router.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user("operator", user_id=101)
    app.dependency_overrides[get_async_db] = _override_db
    monkeypatch.setattr(
        "backend.routers.follow_investment.FollowInvestmentService",
        lambda db: _ServiceStub(),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/finance/follow-investments/my-income")

    body = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["summary"]["estimated_income"] == 24432
    assert body["data"]["items"][0]["shop_id"] == "shop-1"
