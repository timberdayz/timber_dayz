import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.models.database import get_async_db
from backend.routers import main_accounts
from modules.core.db import MainAccount, ShopAccountAlias, ShopAccountCapability


@pytest_asyncio.fixture
async def main_account_client(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS core")
        await conn.run_sync(MainAccount.__table__.create)
        await conn.run_sync(ShopAccountAlias.__table__.create)
        await conn.run_sync(ShopAccountCapability.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    app = FastAPI()
    app.include_router(main_accounts.router, prefix="/api")

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
async def test_create_main_account(main_account_client):
    response = await main_account_client.post(
        "/api/main-accounts",
        json={
            "platform": "shopee",
            "main_account_id": "hongxikeji:main",
            "main_account_name": "Shopee 新加坡主体",
            "username": "demo-user",
            "password": "plain-password",
            "login_url": "https://seller.shopee.cn",
            "enabled": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["main_account_id"] == "hongxikeji:main"
    assert payload["main_account_name"] == "Shopee 新加坡主体"
    assert payload["platform"] == "shopee"
    assert "cnsc_shop_id=" not in (payload["login_url"] or "")


@pytest.mark.asyncio
async def test_create_main_account_repairs_mojibake_name(main_account_client):
    response = await main_account_client.post(
        "/api/main-accounts",
        json={
            "platform": "shopee",
            "main_account_id": "repair:main",
            "main_account_name": "3Cåº\x97",
            "username": "demo-user",
            "password": "plain-password",
            "enabled": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["main_account_name"] == "3C店"


@pytest.mark.asyncio
async def test_create_main_account_uses_notes_when_name_is_placeholder(main_account_client):
    response = await main_account_client.post(
        "/api/main-accounts",
        json={
            "platform": "shopee",
            "main_account_id": "fallback:main",
            "main_account_name": "Shopee ???? (2?)",
            "username": "demo-user",
            "password": "plain-password",
            "enabled": True,
            "notes": "shopee新加坡3C店",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["main_account_name"] == "shopee新加坡3C店"


@pytest.mark.asyncio
async def test_create_main_account_normalizes_shop_bound_login_url(main_account_client):
    response = await main_account_client.post(
        "/api/main-accounts",
        json={
            "platform": "shopee",
            "main_account_id": "normalize:main",
            "main_account_name": "Shopee Main",
            "username": "demo-user",
            "password": "plain-password",
            "login_url": "https://seller.shopee.cn/account/signin?next=%2Fportal%2Fproduct%2Flist%2Fall%3Fcnsc_shop_id%3D1407964586%26page%3D1",
            "enabled": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["login_url"] == "https://seller.shopee.cn/account/signin?next=%2Fportal%2Fhome"
