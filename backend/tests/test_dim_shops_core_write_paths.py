import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.services.shop_sync_service import sync_platform_account_to_dim_shop
from modules.core.db import Base, DimPlatform, DimShop, PlatformAccount


@pytest_asyncio.fixture
async def dim_shops_core_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_shop_sync_creates_dim_shop_in_core_schema(dim_shops_core_session):
    platform = DimPlatform(platform_code="shopee", name="Shopee", is_active=True)
    account = PlatformAccount(
        account_id="acc-1",
        platform="shopee",
        shop_id="shop-1",
        store_name="Test Shop",
        username="shop-sync-1",
        password_encrypted="encrypted",
        currency="SGD",
    )
    dim_shops_core_session.add(platform)
    dim_shops_core_session.add(account)
    await dim_shops_core_session.commit()

    created = await sync_platform_account_to_dim_shop(dim_shops_core_session, account)
    await dim_shops_core_session.commit()

    loaded = (
        await dim_shops_core_session.execute(
            select(DimShop).where(
                DimShop.platform_code == "shopee",
                DimShop.shop_id == "shop-1",
            )
        )
    ).scalar_one()

    assert created is not None
    assert loaded.shop_name == "Test Shop"
    assert loaded.__table__.schema == "core"


@pytest.mark.asyncio
async def test_shop_sync_updates_existing_core_dim_shop(dim_shops_core_session):
    platform = DimPlatform(platform_code="shopee", name="Shopee", is_active=True)
    existing_shop = DimShop(
        platform_code="shopee",
        shop_id="shop-2",
        shop_name="Old Name",
        shop_slug="old-shop",
        currency="USD",
    )
    account = PlatformAccount(
        account_id="acc-2",
        platform="shopee",
        shop_id="shop-2",
        store_name="New Name",
        username="shop-sync-2",
        password_encrypted="encrypted",
        currency="MYR",
    )
    dim_shops_core_session.add(platform)
    dim_shops_core_session.add(existing_shop)
    dim_shops_core_session.add(account)
    await dim_shops_core_session.commit()

    await sync_platform_account_to_dim_shop(dim_shops_core_session, account)
    await dim_shops_core_session.commit()

    loaded = (
        await dim_shops_core_session.execute(
            select(DimShop).where(
                DimShop.platform_code == "shopee",
                DimShop.shop_id == "shop-2",
            )
        )
    ).scalar_one()

    assert loaded.shop_name == "New Name"
    assert loaded.currency == "MYR"
