from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


def _make_user(role: str = "operator", *, is_superuser: bool = False):
    return SimpleNamespace(
        user_id=1,
        id=1,
        username=f"{role}_user",
        is_active=True,
        status="active",
        is_superuser=is_superuser,
        roles=[SimpleNamespace(role_code=role, role_name=role)],
    )


@pytest_asyncio.fixture
async def auth_contract_client():
    from backend.main import app
    from backend.models.database import get_async_db

    async def override_get_async_db():
        yield SimpleNamespace()

    app.dependency_overrides[get_async_db] = override_get_async_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "post",
            "/api/collection/configs",
            {
                "name": "auth-check-config",
                "platform": "shopee",
                "account_ids": ["acc-1"],
                "data_domains": ["orders"],
                "granularity": "daily",
                "time_selection": {"mode": "preset", "preset": "yesterday"},
                "schedule_enabled": False,
                "retry_count": 3,
            },
        ),
        (
            "get",
            "/api/collection/config-coverage",
            None,
        ),
        (
            "post",
            "/api/main-accounts",
            {
                "platform": "shopee",
                "main_account_id": "auth-check:main",
                "username": "demo-user",
                "password": "plain-password",
                "enabled": True,
            },
        ),
        (
            "post",
            "/api/shop-accounts",
            {
                "platform": "shopee",
                "shop_account_id": "auth-check-shop",
                "main_account_id": "auth-check:main",
                "store_name": "Auth Check Shop",
                "enabled": True,
            },
        ),
        (
            "post",
            "/api/platform-shop-discoveries/1/confirm",
            {"shop_account_id": "shop-1"},
        ),
        (
            "post",
            "/api/account-alignment/add-alias",
            {
                "account": "acc-1",
                "site": "SG",
                "store_label_raw": "Raw Store",
                "target_id": "target-store",
            },
        ),
        (
            "get",
            "/api/component-versions",
            None,
        ),
        (
            "post",
            "/api/collection/recorder/start",
            {
                "platform": "miaoshou",
                "component_type": "export",
                "account_id": "acc-1",
            },
        ),
    ],
)
async def test_high_risk_admin_routes_require_authentication(
    auth_contract_client: AsyncClient,
    method: str,
    path: str,
    payload,
):
    request = getattr(auth_contract_client, method)
    response = (
        await request(path, json=payload)
        if payload is not None
        else await request(path)
    )

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "post",
            "/api/collection/configs",
            {
                "name": "auth-check-config",
                "platform": "shopee",
                "account_ids": ["acc-1"],
                "data_domains": ["orders"],
                "granularity": "daily",
                "time_selection": {"mode": "preset", "preset": "yesterday"},
                "schedule_enabled": False,
                "retry_count": 3,
            },
        ),
        ("get", "/api/collection/config-coverage", None),
        (
            "post",
            "/api/main-accounts",
            {
                "platform": "shopee",
                "main_account_id": "auth-check:main",
                "username": "demo-user",
                "password": "plain-password",
                "enabled": True,
            },
        ),
        (
            "post",
            "/api/shop-accounts",
            {
                "platform": "shopee",
                "shop_account_id": "auth-check-shop",
                "main_account_id": "auth-check:main",
                "store_name": "Auth Check Shop",
                "enabled": True,
            },
        ),
        (
            "post",
            "/api/platform-shop-discoveries/1/confirm",
            {"shop_account_id": "shop-1"},
        ),
        (
            "post",
            "/api/account-alignment/add-alias",
            {
                "account": "acc-1",
                "site": "SG",
                "store_label_raw": "Raw Store",
                "target_id": "target-store",
            },
        ),
        ("get", "/api/component-versions", None),
        (
            "post",
            "/api/collection/recorder/start",
            {
                "platform": "miaoshou",
                "component_type": "export",
                "account_id": "acc-1",
            },
        ),
    ],
)
async def test_high_risk_admin_routes_reject_non_admin_users(
    auth_contract_client: AsyncClient,
    method: str,
    path: str,
    payload,
):
    from backend.dependencies.auth import get_current_user
    from backend.main import app

    async def override_current_user():
        return _make_user("operator")

    app.dependency_overrides[get_current_user] = override_current_user

    request = getattr(auth_contract_client, method)
    response = (
        await request(path, json=payload)
        if payload is not None
        else await request(path)
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_inventory_view_routes_require_authenticated_user(auth_contract_client: AsyncClient):
    balances = await auth_contract_client.get("/api/inventory/balances")
    overview = await auth_contract_client.get("/api/inventory-overview/summary")

    assert balances.status_code == 401
    assert overview.status_code == 401


@pytest.mark.asyncio
async def test_inventory_view_routes_allow_non_admin_authenticated_user(
    auth_contract_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    from backend.dependencies.auth import get_current_user
    from backend.main import app

    async def override_current_user():
        return _make_user("operator")

    app.dependency_overrides[get_current_user] = override_current_user
    monkeypatch.setattr(
        "backend.routers.inventory_domain.InventoryBalanceService.list_balances",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "backend.routers.inventory_overview.InventoryOverviewService.get_summary",
        AsyncMock(
            return_value={
                "total_products": 0,
                "total_stock": 0,
                "total_value": 0,
                "low_stock_count": 0,
                "out_of_stock_count": 0,
                "high_risk_sku_count": 0,
                "medium_risk_sku_count": 0,
                "low_risk_sku_count": 0,
                "platform_breakdown": [],
            }
        ),
    )

    balances = await auth_contract_client.get("/api/inventory/balances")
    overview = await auth_contract_client.get("/api/inventory-overview/summary")

    assert balances.status_code == 200
    assert overview.status_code == 200


@pytest.mark.asyncio
async def test_inventory_write_routes_require_admin(
    auth_contract_client: AsyncClient,
):
    payload = {
        "adjustment_date": "2026-04-06",
        "reason": "stock_count",
        "lines": [
            {
                "platform_code": "shopee",
                "shop_id": "shop-1",
                "platform_sku": "SKU-1",
                "qty_delta": 1,
            }
        ],
    }

    unauthenticated = await auth_contract_client.post("/api/inventory/adjustments", json=payload)
    assert unauthenticated.status_code == 401

    from backend.dependencies.auth import get_current_user
    from backend.main import app

    async def override_current_user():
        return _make_user("operator")

    app.dependency_overrides[get_current_user] = override_current_user
    forbidden = await auth_contract_client.post("/api/inventory/adjustments", json=payload)

    assert forbidden.status_code == 403
