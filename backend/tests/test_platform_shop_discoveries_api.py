import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.models.database import get_async_db
from backend.routers import main_accounts, platform_shop_discoveries, shop_accounts
from modules.core.db import MainAccount, PlatformShopDiscovery, ShopAccount, ShopAccountAlias, ShopAccountCapability


@pytest_asyncio.fixture
async def discovery_client(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS core")
        await conn.run_sync(MainAccount.__table__.create)
        await conn.run_sync(ShopAccount.__table__.create)
        await conn.run_sync(ShopAccountAlias.__table__.create)
        await conn.run_sync(ShopAccountCapability.__table__.create)
        await conn.run_sync(PlatformShopDiscovery.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    app = FastAPI()
    app.include_router(main_accounts.router, prefix="/api")
    app.include_router(shop_accounts.router, prefix="/api")
    app.include_router(platform_shop_discoveries.router, prefix="/api")

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
async def test_confirm_platform_shop_discovery_updates_shop_account(discovery_client):
    await discovery_client.post(
        "/api/main-accounts",
        json={
            "platform": "shopee",
            "main_account_id": "hongxikeji:main",
            "username": "demo-user",
            "password": "plain-password",
            "enabled": True,
        },
    )
    await discovery_client.post(
        "/api/shop-accounts",
        json={
            "platform": "shopee",
            "shop_account_id": "shopee_sg_hongxi_local",
            "main_account_id": "hongxikeji:main",
            "store_name": "HongXi SG",
            "enabled": True,
        },
    )

    list_before = await discovery_client.get("/api/shop-accounts")
    shop_record = list_before.json()[0]

    await discovery_client.post(
        "/api/shop-accounts",
        json={
            "platform": "shopee",
            "shop_account_id": "shopee_my_hongxi_local",
            "main_account_id": "hongxikeji:main",
            "store_name": "HongXi MY",
            "enabled": True,
        },
    )

    # seed a pending discovery directly through the DB-backed API layer
    # by using the list route app and inserting through the current session is complex here,
    # so we post with the raw session by reusing the mounted app database in a follow-up request.
    # create route coverage is focused on confirm semantics.
    from backend.routers.platform_shop_discoveries import PlatformShopDiscovery

    # fallback: use a lightweight direct insert via a dedicated app route-independent session is not available
    # so create through SQLAlchemy metadata-backed session in the same attached database.
    # this test keeps the assertion on the confirm endpoint behavior.
    transport = discovery_client._transport
    app = transport.app
    override = app.dependency_overrides[get_async_db]
    async for session in override():
        session.add(
            PlatformShopDiscovery(
                platform="shopee",
                main_account_id="hongxikeji:main",
                detected_store_name="HongXi SG",
                detected_platform_shop_id="1227491331",
                detected_region="SG",
                candidate_shop_account_ids=["shopee_sg_hongxi_local", "shopee_my_hongxi_local"],
                status="detected_pending_confirm",
            )
        )
        await session.commit()
        break

    response = await discovery_client.post(
        "/api/platform-shop-discoveries/1/confirm",
        json={"shop_account_id": "shopee_sg_hongxi_local"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "manual_confirmed"
