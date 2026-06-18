import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.models.database import get_async_db
from backend.routers import main_accounts, shop_accounts
from modules.core.db import MainAccount, ShopAccount, ShopAccountAlias, ShopAccountCapability


class _FakeBusinessOverviewCache:
    def __init__(self, calls):
        self.calls = calls

    async def invalidate_dashboard_business_overview(self):
        self.calls.append("invalidate_dashboard_business_overview")
        return 0


class _FakeRefreshQueueService:
    calls = []

    def __init__(self, db):
        self.db = db

    async def enqueue_refresh(self, **kwargs):
        self.calls.append(kwargs)
        return type("Task", (), {"job_id": "refresh-test"})()


@pytest_asyncio.fixture
async def shop_account_client(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS core")
        await conn.run_sync(MainAccount.__table__.create)
        await conn.run_sync(ShopAccount.__table__.create)
        await conn.run_sync(ShopAccountAlias.__table__.create)
        await conn.run_sync(ShopAccountCapability.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    app = FastAPI()
    app.include_router(main_accounts.router, prefix="/api")
    app.include_router(shop_accounts.router, prefix="/api")

    async def override_get_async_db():
        async with session_factory() as session:
            yield session

    async def override_current_user():
        return type(
            "AdminUser",
            (),
            {
                "user_id": 1,
                "id": 1,
                "username": "admin",
                "is_active": True,
                "status": "active",
                "is_superuser": True,
                "roles": [type("Role", (), {"role_code": "admin", "role_name": "admin"})()],
            },
        )()

    app.dependency_overrides[get_async_db] = override_get_async_db
    from backend.dependencies.auth import get_current_user
    app.dependency_overrides[get_current_user] = override_current_user
    monkeypatch.setattr(
        "backend.routers.main_accounts.get_encryption_service",
        lambda: type("Enc", (), {"encrypt_password": lambda self, value: f"enc:{value}"})(),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    await engine.dispose()


@pytest.mark.asyncio
async def test_batch_create_shop_accounts_under_main_account(shop_account_client):
    create_main = await shop_account_client.post(
        "/api/main-accounts",
        json={
            "platform": "shopee",
            "main_account_id": "hongxikeji:main",
            "username": "demo-user",
            "password": "plain-password",
            "login_url": "https://seller.shopee.cn",
            "enabled": True,
        },
    )
    assert create_main.status_code == 200

    response = await shop_account_client.post(
        "/api/shop-accounts/batch",
        json=[
            {
                "platform": "shopee",
                "shop_account_id": "shopee_sg_hongxi_local",
                "main_account_id": "hongxikeji:main",
                "store_name": "HongXi SG",
                "shop_region": "SG",
                "shop_type": "local",
                "enabled": True,
            },
            {
                "platform": "shopee",
                "shop_account_id": "shopee_my_hongxi_local",
                "main_account_id": "hongxikeji:main",
                "store_name": "HongXi MY",
                "shop_region": "MY",
                "shop_type": "local",
                "enabled": True,
            },
        ],
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["main_account_id"] == "hongxikeji:main"
    assert payload[0]["capabilities"]["orders"] is True
    assert payload[0]["capabilities"]["services"] is True


@pytest.mark.asyncio
async def test_create_shop_account_assigns_default_capabilities(shop_account_client):
    create_main = await shop_account_client.post(
        "/api/main-accounts",
        json={
            "platform": "shopee",
            "main_account_id": "hongxikeji:main",
            "username": "demo-user",
            "password": "plain-password",
            "enabled": True,
        },
    )
    assert create_main.status_code == 200

    response = await shop_account_client.post(
        "/api/shop-accounts",
        json={
            "platform": "shopee",
            "shop_account_id": "shopee_sg_hongxi_local",
            "main_account_id": "hongxikeji:main",
            "store_name": "HongXi SG",
            "shop_region": "SG",
            "shop_type": "local",
            "enabled": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["capabilities"] == {
        "orders": True,
        "products": True,
        "services": True,
        "analytics": True,
        "finance": True,
        "inventory": True,
    }


@pytest.mark.asyncio
async def test_update_shop_account_persists_capabilities(shop_account_client):
    create_main = await shop_account_client.post(
        "/api/main-accounts",
        json={
            "platform": "shopee",
            "main_account_id": "hongxikeji:main",
            "username": "demo-user",
            "password": "plain-password",
            "enabled": True,
        },
    )
    assert create_main.status_code == 200

    create_shop = await shop_account_client.post(
        "/api/shop-accounts",
        json={
            "platform": "shopee",
            "shop_account_id": "shopee_sg_hongxi_local",
            "main_account_id": "hongxikeji:main",
            "store_name": "HongXi SG",
            "shop_region": "SG",
            "shop_type": "local",
            "enabled": True,
        },
    )
    assert create_shop.status_code == 200

    update_response = await shop_account_client.put(
        "/api/shop-accounts/shopee_sg_hongxi_local",
        json={
            "capabilities": {
                "orders": True,
                "products": False,
                "services": False,
                "analytics": True,
                "finance": False,
                "inventory": True,
            }
        },
    )

    assert update_response.status_code == 200
    updated_payload = update_response.json()
    assert updated_payload["capabilities"] == {
        "orders": True,
        "products": False,
        "services": False,
        "analytics": True,
        "finance": False,
        "inventory": True,
    }

    list_response = await shop_account_client.get("/api/shop-accounts")
    assert list_response.status_code == 200
    listed_account = list_response.json()[0]
    assert listed_account["capabilities"] == {
        "orders": True,
        "products": False,
        "services": False,
        "analytics": True,
        "finance": False,
        "inventory": True,
    }


@pytest.mark.asyncio
async def test_update_shop_account_returns_409_when_platform_shop_id_conflicts(shop_account_client):
    create_main = await shop_account_client.post(
        "/api/main-accounts",
        json={
            "platform": "shopee",
            "main_account_id": "hongxikeji:main",
            "username": "demo-user",
            "password": "plain-password",
            "enabled": True,
        },
    )
    assert create_main.status_code == 200

    first_shop = await shop_account_client.post(
        "/api/shop-accounts",
        json={
            "platform": "shopee",
            "shop_account_id": "shopee_existing_shop",
            "main_account_id": "hongxikeji:main",
            "store_name": "Existing Shop",
            "platform_shop_id": "xihong",
            "shop_region": "MY",
            "shop_type": "local",
            "enabled": True,
        },
    )
    assert first_shop.status_code == 200

    second_shop = await shop_account_client.post(
        "/api/shop-accounts",
        json={
            "platform": "shopee",
            "shop_account_id": "shopee_target_shop",
            "main_account_id": "hongxikeji:main",
            "store_name": "Target Shop",
            "shop_region": "MY",
            "shop_type": "local",
            "enabled": True,
        },
    )
    assert second_shop.status_code == 200

    update_response = await shop_account_client.put(
        "/api/shop-accounts/shopee_target_shop",
        json={
            "platform_shop_id": "xihong",
            "platform_shop_id_status": "manual_confirmed",
        },
    )

    assert update_response.status_code == 409
    assert "platform_shop_id 'xihong'" in update_response.json()["detail"]


@pytest.mark.asyncio
async def test_update_shop_identity_enqueues_business_overview_refresh_and_invalidates_cache(
    shop_account_client,
    monkeypatch,
):
    refresh_calls = []
    cache_calls = []

    class FakeRefreshQueueService(_FakeRefreshQueueService):
        calls = refresh_calls

    monkeypatch.setattr(
        "backend.domains.collection.routers.shop_accounts.RefreshQueueService",
        FakeRefreshQueueService,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.domains.collection.routers.shop_accounts.get_cache_service",
        lambda: _FakeBusinessOverviewCache(cache_calls),
        raising=False,
    )

    create_main = await shop_account_client.post(
        "/api/main-accounts",
        json={
            "platform": "shopee",
            "main_account_id": "hongxikeji:main",
            "username": "demo-user",
            "password": "plain-password",
            "enabled": True,
        },
    )
    assert create_main.status_code == 200
    create_shop = await shop_account_client.post(
        "/api/shop-accounts",
        json={
            "platform": "shopee",
            "shop_account_id": "shopee_sg_hongxi_local",
            "main_account_id": "hongxikeji:main",
            "store_name": "HongXi SG",
            "enabled": True,
        },
    )
    assert create_shop.status_code == 200

    update_response = await shop_account_client.put(
        "/api/shop-accounts/shopee_sg_hongxi_local",
        json={
            "store_name": "HongXi SG Official",
            "platform_shop_id": "1227492331",
            "platform_shop_id_status": "manual_confirmed",
        },
    )

    assert update_response.status_code == 200
    assert len(refresh_calls) == 1
    assert refresh_calls[0]["trigger_type"] == "shop_identity_changed"
    assert refresh_calls[0]["pipeline_name"] == "postgresql_dashboard"
    assert "semantic.fact_orders_monthly_atomic_mv" in refresh_calls[0]["targets"]
    assert "semantic.fact_analytics_monthly_atomic_mv" in refresh_calls[0]["targets"]
    assert refresh_calls[0]["context"]["shop_account_id"] == "shopee_sg_hongxi_local"
    assert refresh_calls[0]["context"]["changed_fields"] == [
        "store_name",
        "platform_shop_id",
        "platform_shop_id_status",
    ]
    assert cache_calls == ["invalidate_dashboard_business_overview"]
