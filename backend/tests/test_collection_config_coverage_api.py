import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import CollectionConfig, MainAccount, ShopAccount, ShopAccountCapability


@pytest_asyncio.fixture
async def collection_coverage_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(MainAccount.__table__.create)
        await conn.run_sync(ShopAccount.__table__.create)
        await conn.run_sync(ShopAccountCapability.__table__.create)
        await conn.run_sync(CollectionConfig.__table__.create)

    yield engine
    await engine.dispose()


@pytest.fixture
def collection_coverage_session_factory(collection_coverage_engine):
    return async_sessionmaker(collection_coverage_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def collection_coverage_session(collection_coverage_session_factory):
    async with collection_coverage_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def collection_coverage_client(collection_coverage_session):
    from backend.main import app
    from backend.models.database import get_async_db

    async def override_get_async_db():
        yield collection_coverage_session

    app.dependency_overrides[get_async_db] = override_get_async_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client
    app.dependency_overrides.pop(get_async_db, None)


async def _seed_accounts(session):
    main_records = [
        MainAccount(
            platform="shopee",
            main_account_id="main-a",
            main_account_name="Shopee SG Main",
            username="sg-main",
            password_encrypted="enc",
            enabled=True,
        ),
        MainAccount(
            platform="tiktok",
            main_account_id="main-b",
            main_account_name="TikTok SEA Main",
            username="sea-main",
            password_encrypted="enc",
            enabled=True,
        ),
    ]
    for record in main_records:
        session.add(record)
    await session.flush()

    shops = [
        ShopAccount(
            platform="shopee",
            shop_account_id="shop-sg-1",
            main_account_id="main-a",
            store_name="Shop SG 1",
            shop_region="SG",
            shop_type="local",
            enabled=True,
        ),
        ShopAccount(
            platform="shopee",
            shop_account_id="shop-my-1",
            main_account_id="main-a",
            store_name="Shop MY 1",
            shop_region="MY",
            shop_type="local",
            enabled=True,
        ),
        ShopAccount(
            platform="tiktok",
            shop_account_id="shop-ph-1",
            main_account_id="main-b",
            store_name="Shop PH 1",
            shop_region="PH",
            shop_type="global",
            enabled=True,
        ),
    ]
    for shop in shops:
        session.add(shop)
    await session.flush()

    shop_by_id = {shop.shop_account_id: shop for shop in shops}

    capability_rows = [
        ShopAccountCapability(shop_account_id=shop_by_id["shop-sg-1"].id, data_domain="orders", enabled=True),
        ShopAccountCapability(shop_account_id=shop_by_id["shop-sg-1"].id, data_domain="products", enabled=True),
        ShopAccountCapability(shop_account_id=shop_by_id["shop-my-1"].id, data_domain="orders", enabled=True),
    ]
    for row in capability_rows:
        session.add(row)

    configs = [
        CollectionConfig(
            name="daily-shop-sg-1",
            platform="shopee",
            account_ids=["shop-sg-1"],
            data_domains=["orders"],
            granularity="daily",
            date_range_type="today",
            schedule_enabled=False,
            retry_count=3,
            execution_mode="headless",
            is_active=True,
        ),
        CollectionConfig(
            name="weekly-shop-sg-1",
            platform="shopee",
            account_ids=["shop-sg-1"],
            data_domains=["orders"],
            granularity="weekly",
            date_range_type="last_7_days",
            schedule_enabled=False,
            retry_count=3,
            execution_mode="headed",
            is_active=True,
        ),
        CollectionConfig(
            name="monthly-shop-my-1",
            platform="shopee",
            account_ids=["shop-my-1"],
            data_domains=["orders"],
            granularity="monthly",
            date_range_type="last_30_days",
            schedule_enabled=False,
            retry_count=3,
            execution_mode="headless",
            is_active=True,
        ),
    ]
    for config in configs:
        session.add(config)

    await session.commit()


@pytest.mark.asyncio
async def test_collection_accounts_grouped_expose_main_account_region_and_capabilities(
    collection_coverage_client,
    collection_coverage_session,
):
    await _seed_accounts(collection_coverage_session)

    response = await collection_coverage_client.get("/api/collection/accounts/grouped")

    assert response.status_code == 200
    body = response.json()

    assert len(body) == 2
    assert body[0]["platform"] == "shopee"
    assert body[0]["main_account_id"] == "main-a"
    assert body[0]["main_account_name"] == "Shopee SG Main"
    assert body[0]["regions"][0]["shop_region"] == "MY"
    assert body[0]["regions"][1]["shop_region"] == "SG"
    assert body[0]["regions"][1]["shops"][0]["id"] == "shop-sg-1"
    assert body[0]["regions"][1]["shops"][0]["capabilities"]["orders"] is True


@pytest.mark.asyncio
async def test_collection_config_coverage_reports_missing_granularities_per_shop(
    collection_coverage_client,
    collection_coverage_session,
):
    await _seed_accounts(collection_coverage_session)

    response = await collection_coverage_client.get("/api/collection/config-coverage")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["daily_missing_count"] == 2
    assert body["summary"]["weekly_missing_count"] == 2
    assert body["summary"]["monthly_missing_count"] == 2
    assert body["summary"]["daily_covered_count"] == 1
    assert body["summary"]["weekly_covered_count"] == 1
    assert body["summary"]["monthly_covered_count"] == 1
    assert body["summary"]["partial_covered_count"] == 2

    coverage_by_shop = {item["shop_account_id"]: item for item in body["items"]}

    sg = coverage_by_shop["shop-sg-1"]
    assert sg["daily_covered"] is True
    assert sg["weekly_covered"] is True
    assert sg["monthly_covered"] is False
    assert sg["missing_granularities"] == ["monthly"]
    assert sg["is_partially_covered"] is True
    assert sg["recommended_domains"] == ["orders", "products"]

    my = coverage_by_shop["shop-my-1"]
    assert my["daily_covered"] is False
    assert my["weekly_covered"] is False
    assert my["monthly_covered"] is True
    assert my["missing_granularities"] == ["daily", "weekly"]
    assert my["is_partially_covered"] is True
    assert my["recommended_domains"] == ["orders"]

    ph = coverage_by_shop["shop-ph-1"]
    assert ph["daily_covered"] is False
    assert ph["weekly_covered"] is False
    assert ph["monthly_covered"] is False
    assert ph["missing_granularities"] == ["daily", "weekly", "monthly"]
    assert ph["is_partially_covered"] is False
    assert ph["recommended_domains"] == ["analytics", "finance", "inventory", "orders", "products"]
