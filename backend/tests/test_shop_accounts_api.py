import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.models.database import get_async_db
from backend.routers import main_accounts, shop_accounts
from modules.core.db import MainAccount, ShopAccount, ShopAccountAlias, ShopAccountCapability


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

    app.dependency_overrides[get_async_db] = override_get_async_db
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
