import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.services.collection_config_execution import create_tasks_for_config
from modules.core.db import (
    CollectionConfig,
    CollectionConfigShopScope,
    CollectionTask,
    MainAccount,
    ShopAccount,
    ShopAccountCapability,
)


@pytest_asyncio.fixture
async def config_execution_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(MainAccount.__table__.create)
        await conn.run_sync(ShopAccount.__table__.create)
        await conn.run_sync(ShopAccountCapability.__table__.create)
        await conn.run_sync(CollectionConfig.__table__.create)
        await conn.run_sync(CollectionConfigShopScope.__table__.create)
        await conn.run_sync(CollectionTask.__table__.create)

    yield engine
    await engine.dispose()


@pytest.fixture
def config_execution_session_factory(config_execution_engine):
    return async_sessionmaker(config_execution_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def config_execution_session(config_execution_session_factory):
    async with config_execution_session_factory() as session:
        yield session


async def _seed_config(session):
    main_account = MainAccount(
        platform="shopee",
        main_account_id="main-shopee",
        main_account_name="Shopee Main",
        username="shopee-main",
        password_encrypted="enc",
        enabled=True,
    )
    session.add(main_account)
    await session.flush()

    shops = [
        ShopAccount(
            platform="shopee",
            shop_account_id="shop-sg-1",
            main_account_id="main-shopee",
            store_name="Shop SG 1",
            platform_shop_id="platform-sg-1",
            shop_region="SG",
            shop_type="local",
            enabled=True,
        ),
        ShopAccount(
            platform="shopee",
            shop_account_id="shop-my-1",
            main_account_id="main-shopee",
            store_name="Shop MY 1",
            platform_shop_id="platform-my-1",
            shop_region="MY",
            shop_type="local",
            enabled=True,
        ),
    ]
    session.add_all(shops)
    await session.flush()

    id_map = {shop.shop_account_id: shop.id for shop in shops}
    session.add_all(
        [
            ShopAccountCapability(shop_account_id=id_map["shop-sg-1"], data_domain="orders", enabled=True),
            ShopAccountCapability(shop_account_id=id_map["shop-sg-1"], data_domain="services", enabled=True),
            ShopAccountCapability(shop_account_id=id_map["shop-my-1"], data_domain="products", enabled=True),
        ]
    )

    config = CollectionConfig(
        name="shopee-daily-v1",
        platform="shopee",
        account_ids=["shop-sg-1", "shop-my-1"],
        data_domains=["orders", "products", "services"],
        sub_domains={"services": ["agent"]},
        granularity="daily",
        date_range_type="yesterday",
        schedule_enabled=False,
        schedule_cron=None,
        retry_count=3,
        execution_mode="headless",
        is_active=True,
    )
    session.add(config)
    await session.flush()
    session.add_all(
        [
            CollectionConfigShopScope(
                config_id=config.id,
                shop_account_id="shop-sg-1",
                data_domains=["orders", "services"],
                sub_domains={"services": ["agent"]},
                enabled=True,
            ),
            CollectionConfigShopScope(
                config_id=config.id,
                shop_account_id="shop-my-1",
                data_domains=["products", "services"],
                sub_domains={"services": ["agent"]},
                enabled=True,
            ),
        ]
    )
    await session.commit()
    return config.id


@pytest.mark.asyncio
async def test_create_tasks_for_config_expands_per_shop_scope(config_execution_session):
    config_id = await _seed_config(config_execution_session)

    tasks = await create_tasks_for_config(
        config_execution_session,
        config_id=config_id,
        trigger_type="scheduled",
        resolve_runtime=False,
    )

    assert len(tasks) == 2
    task_map = {task.account: task for task in tasks}
    assert task_map["shop-sg-1"].data_domains == ["orders", "services"]
    assert task_map["shop-sg-1"].sub_domains == {"services": ["agent"]}
    assert task_map["shop-my-1"].data_domains == ["products"]
    assert task_map["shop-my-1"].sub_domains is None


@pytest.mark.asyncio
async def test_create_tasks_for_config_skips_conflicted_shop_without_blocking_others(config_execution_session):
    config_id = await _seed_config(config_execution_session)

    config_result = await config_execution_session.execute(select(CollectionConfig).where(CollectionConfig.id == config_id))
    config = config_result.scalar_one()
    config_execution_session.add(
        CollectionTask(
            task_id="existing-running-task",
            config_id=config.id,
            platform=config.platform,
            account="shop-sg-1",
            status="running",
            progress=50,
            trigger_type="scheduled",
            data_domains=["orders"],
            sub_domains=None,
            granularity="daily",
            date_range={"start_date": "2026-04-01", "end_date": "2026-04-01"},
            total_domains=1,
            completed_domains=[],
            failed_domains=[],
            current_domain="orders",
            debug_mode=False,
        )
    )
    await config_execution_session.commit()

    tasks = await create_tasks_for_config(
        config_execution_session,
        config_id=config_id,
        trigger_type="scheduled",
        resolve_runtime=False,
    )

    assert len(tasks) == 1
    assert tasks[0].account == "shop-my-1"
