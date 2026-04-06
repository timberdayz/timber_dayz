import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import CollectionConfig, CollectionConfigShopScope, CollectionTask


@pytest_asyncio.fixture
async def collection_shop_scope_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(CollectionConfig.__table__.create)
        await conn.run_sync(CollectionConfigShopScope.__table__.create)
        await conn.run_sync(CollectionTask.__table__.create)

    yield engine
    await engine.dispose()


@pytest.fixture
def collection_shop_scope_session_factory(collection_shop_scope_engine):
    return async_sessionmaker(collection_shop_scope_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def collection_shop_scope_session(collection_shop_scope_session_factory):
    async with collection_shop_scope_session_factory() as session:
        yield session


@pytest.mark.asyncio
async def test_collection_config_can_own_multiple_shop_scopes(collection_shop_scope_session):
    config = CollectionConfig(
        name="shopee-daily-v1",
        platform="shopee",
        account_ids=[],
        data_domains=[],
        sub_domains=None,
        granularity="daily",
        date_range_type="yesterday",
        schedule_enabled=False,
        schedule_cron=None,
        retry_count=3,
        execution_mode="headless",
        is_active=True,
    )
    collection_shop_scope_session.add(config)
    await collection_shop_scope_session.flush()

    collection_shop_scope_session.add_all(
        [
            CollectionConfigShopScope(
                config_id=config.id,
                shop_account_id="shop-sg-1",
                data_domains=["orders", "products"],
                sub_domains={"services": ["agent"]},
                enabled=True,
            ),
            CollectionConfigShopScope(
                config_id=config.id,
                shop_account_id="shop-my-1",
                data_domains=["products"],
                sub_domains=None,
                enabled=True,
            ),
        ]
    )
    await collection_shop_scope_session.commit()

    result = await collection_shop_scope_session.execute(
        select(CollectionConfigShopScope).where(CollectionConfigShopScope.config_id == config.id)
    )
    scopes = result.scalars().all()

    assert len(scopes) == 2
    assert {scope.shop_account_id for scope in scopes} == {"shop-sg-1", "shop-my-1"}


@pytest.mark.asyncio
async def test_deleting_collection_config_removes_shop_scopes(collection_shop_scope_session):
    config = CollectionConfig(
        name="shopee-weekly-v1",
        platform="shopee",
        account_ids=[],
        data_domains=[],
        sub_domains=None,
        granularity="weekly",
        date_range_type="last_7_days",
        schedule_enabled=False,
        schedule_cron=None,
        retry_count=3,
        execution_mode="headless",
        is_active=True,
    )
    collection_shop_scope_session.add(config)
    await collection_shop_scope_session.flush()

    scope = CollectionConfigShopScope(
        config_id=config.id,
        shop_account_id="shop-sg-1",
        data_domains=["orders"],
        sub_domains=None,
        enabled=True,
    )
    collection_shop_scope_session.add(scope)
    await collection_shop_scope_session.commit()

    await collection_shop_scope_session.delete(config)
    await collection_shop_scope_session.commit()

    remaining = await collection_shop_scope_session.execute(select(CollectionConfigShopScope))
    assert remaining.scalars().all() == []
