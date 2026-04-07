import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import MainAccount, ShopAccount, ShopAccountCapability


@pytest_asyncio.fixture
async def collection_accounts_guard_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(MainAccount.__table__.create)
        await conn.run_sync(ShopAccount.__table__.create)
        await conn.run_sync(ShopAccountCapability.__table__.create)

    yield engine
    await engine.dispose()


@pytest.fixture
def collection_accounts_guard_session_factory(collection_accounts_guard_engine):
    return async_sessionmaker(collection_accounts_guard_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def collection_accounts_guard_session(collection_accounts_guard_session_factory):
    async with collection_accounts_guard_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def collection_accounts_guard_async_client(collection_accounts_guard_session):
    from backend.main import app
    from backend.dependencies.auth import get_current_user
    from backend.models.database import get_async_db

    async def override_get_async_db():
        yield collection_accounts_guard_session

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
    app.dependency_overrides[get_current_user] = override_current_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client
    app.dependency_overrides.pop(get_async_db, None)
    app.dependency_overrides.pop(get_current_user, None)


async def _seed_accounts(session):
    session.add_all(
        [
            MainAccount(
                platform="shopee",
                main_account_id="main-shopee-a",
                main_account_name="Shopee Main A",
                username="main-a",
                password_encrypted="enc",
                enabled=True,
            ),
            MainAccount(
                platform="shopee",
                main_account_id="main-shopee-b",
                main_account_name="Shopee Main B",
                username="main-b",
                password_encrypted="enc",
                enabled=False,
            ),
        ]
    )
    await session.flush()

    shops = [
        ShopAccount(
            platform="shopee",
            shop_account_id="shop-a-1",
            main_account_id="main-shopee-a",
            store_name="Shop A 1",
            platform_shop_id="platform-a-1",
            shop_region="SG",
            shop_type="local",
            enabled=True,
        ),
        ShopAccount(
            platform="shopee",
            shop_account_id="shop-b-1",
            main_account_id="main-shopee-b",
            store_name="Shop B 1",
            platform_shop_id="platform-b-1",
            shop_region="PH",
            shop_type="local",
            enabled=True,
        ),
    ]
    session.add_all(shops)
    await session.flush()

    session.add_all(
        [
            ShopAccountCapability(shop_account_id=shops[0].id, data_domain="orders", enabled=True),
            ShopAccountCapability(shop_account_id=shops[1].id, data_domain="orders", enabled=True),
        ]
    )
    await session.commit()


@pytest.mark.asyncio
async def test_collection_accounts_excludes_disabled_main_account_shops(
    collection_accounts_guard_async_client,
    collection_accounts_guard_session,
):
    await _seed_accounts(collection_accounts_guard_session)

    response = await collection_accounts_guard_async_client.get(
        "/api/collection/accounts",
        params={"platform": "shopee"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert {item["id"] for item in payload} == {"shop-a-1"}
    assert {item["main_account_id"] for item in payload} == {"main-shopee-a"}
