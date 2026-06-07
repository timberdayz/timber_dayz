import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from types import SimpleNamespace

from backend.services.collection_config_execution import create_tasks_for_config
from backend.services.component_runtime_resolver import NoStableComponentVersionError
from modules.core.db import (
    CollectionConfig,
    CollectionConfigRun,
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
        await conn.run_sync(CollectionConfigRun.__table__.create)
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
        main_account_id="main-shopee",
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


async def _seed_config_run(session, *, config_id: int) -> int:
    config = (
        await session.execute(select(CollectionConfig).where(CollectionConfig.id == config_id))
    ).scalar_one()
    run = CollectionConfigRun(
        run_id="run-1",
        config_id=config.id,
        platform=config.platform,
        main_account_id=config.main_account_id,
        trigger_type="scheduled",
        status="queued",
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run.id


@pytest.mark.asyncio
async def test_create_tasks_for_config_expands_per_shop_scope(config_execution_session):
    config_id = await _seed_config(config_execution_session)
    config_run_id = await _seed_config_run(config_execution_session, config_id=config_id)

    tasks = await create_tasks_for_config(
        config_execution_session,
        config_id=config_id,
        config_run_id=config_run_id,
        trigger_type="scheduled",
        resolve_runtime=False,
    )

    assert len(tasks) == 2
    task_map = {task.account: task for task in tasks}
    assert task_map["shop-sg-1"].data_domains == ["orders", "services"]
    assert task_map["shop-sg-1"].sub_domains == {
        "orders": ["shopee", "tiktok"],
        "services": ["agent"],
    }
    assert task_map["shop-sg-1"].total_domains == 3
    assert task_map["shop-sg-1"].config_run_id == config_run_id
    assert task_map["shop-my-1"].data_domains == ["products"]
    assert task_map["shop-my-1"].sub_domains is None
    assert task_map["shop-my-1"].config_run_id == config_run_id


@pytest.mark.asyncio
async def test_create_tasks_for_config_defaults_order_subtypes_for_config_scopes(
    config_execution_session,
):
    config_id = await _seed_config(config_execution_session)
    config_run_id = await _seed_config_run(config_execution_session, config_id=config_id)

    scope_result = await config_execution_session.execute(
        select(CollectionConfigShopScope).where(
            CollectionConfigShopScope.config_id == config_id,
            CollectionConfigShopScope.shop_account_id == "shop-sg-1",
        )
    )
    scope = scope_result.scalar_one()
    scope.data_domains = ["orders"]
    scope.sub_domains = None
    await config_execution_session.commit()

    tasks = await create_tasks_for_config(
        config_execution_session,
        config_id=config_id,
        config_run_id=config_run_id,
        trigger_type="scheduled",
        resolve_runtime=False,
    )

    task = next(task for task in tasks if task.account == "shop-sg-1")
    assert task.data_domains == ["orders"]
    assert task.sub_domains == {"orders": ["shopee", "tiktok"]}
    assert task.total_domains == 2


@pytest.mark.asyncio
async def test_create_tasks_for_config_preserves_explicit_order_subtype_selection(
    config_execution_session,
):
    config_id = await _seed_config(config_execution_session)
    config_run_id = await _seed_config_run(config_execution_session, config_id=config_id)

    scope_result = await config_execution_session.execute(
        select(CollectionConfigShopScope).where(
            CollectionConfigShopScope.config_id == config_id,
            CollectionConfigShopScope.shop_account_id == "shop-sg-1",
        )
    )
    scope = scope_result.scalar_one()
    scope.data_domains = ["orders"]
    scope.sub_domains = {"orders": ["shopee"]}
    await config_execution_session.commit()

    tasks = await create_tasks_for_config(
        config_execution_session,
        config_id=config_id,
        config_run_id=config_run_id,
        trigger_type="scheduled",
        resolve_runtime=False,
    )

    task = next(task for task in tasks if task.account == "shop-sg-1")
    assert task.sub_domains == {"orders": ["shopee"]}
    assert task.total_domains == 1


@pytest.mark.asyncio
async def test_create_tasks_for_config_skips_conflicted_shop_without_blocking_others(config_execution_session):
    config_id = await _seed_config(config_execution_session)
    config_run_id = await _seed_config_run(config_execution_session, config_id=config_id)

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
        config_run_id=config_run_id,
        trigger_type="scheduled",
        resolve_runtime=False,
    )

    assert len(tasks) == 1
    assert tasks[0].account == "shop-my-1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "active_status",
    ["verification_required", "verification_submitted", "manual_intervention_required"],
)
async def test_create_tasks_for_config_treats_verification_states_as_active_conflicts(
    config_execution_session,
    active_status: str,
):
    config_id = await _seed_config(config_execution_session)
    config_run_id = await _seed_config_run(config_execution_session, config_id=config_id)

    config_result = await config_execution_session.execute(
        select(CollectionConfig).where(CollectionConfig.id == config_id)
    )
    config = config_result.scalar_one()
    config_execution_session.add(
        CollectionTask(
            task_id=f"existing-{active_status}",
            config_id=config.id,
            platform=config.platform,
            account="shop-sg-1",
            status=active_status,
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
        config_run_id=config_run_id,
        trigger_type="scheduled",
        resolve_runtime=False,
    )

    assert len(tasks) == 1
    assert tasks[0].account == "shop-my-1"


@pytest.mark.asyncio
async def test_create_tasks_for_config_does_not_crash_when_multiple_active_tasks_exist_for_same_shop(
    config_execution_session,
):
    config_id = await _seed_config(config_execution_session)
    config_run_id = await _seed_config_run(config_execution_session, config_id=config_id)

    config_result = await config_execution_session.execute(
        select(CollectionConfig).where(CollectionConfig.id == config_id)
    )
    config = config_result.scalar_one()
    config_execution_session.add_all(
        [
            CollectionTask(
                task_id="existing-running-task-a",
                config_id=config.id,
                platform=config.platform,
                account="shop-sg-1",
                status="running",
                progress=20,
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
            ),
            CollectionTask(
                task_id="existing-running-task-b",
                config_id=config.id,
                platform=config.platform,
                account="shop-sg-1",
                status="verification_required",
                progress=30,
                trigger_type="scheduled",
                data_domains=["services"],
                sub_domains={"services": ["agent"]},
                granularity="daily",
                date_range={"start_date": "2026-04-01", "end_date": "2026-04-01"},
                total_domains=1,
                completed_domains=[],
                failed_domains=[],
                current_domain="services",
                debug_mode=False,
            ),
        ]
    )
    await config_execution_session.commit()

    tasks = await create_tasks_for_config(
        config_execution_session,
        config_id=config_id,
        config_run_id=config_run_id,
        trigger_type="scheduled",
        resolve_runtime=False,
    )

    assert len(tasks) == 1
    assert tasks[0].account == "shop-my-1"


@pytest.mark.asyncio
async def test_create_tasks_for_config_prunes_unsupported_subtypes_without_skipping_scope(
    config_execution_session,
    monkeypatch,
):
    config_id = await _seed_config(config_execution_session)
    config_run_id = await _seed_config_run(config_execution_session, config_id=config_id)

    class _FakeResolver:
        async def resolve_login_component(self, platform):
            return {"component_name": f"{platform}/login"}

        async def resolve_export_component(self, *, platform, data_domain, sub_domain):
            if platform == "tiktok" and data_domain == "services" and sub_domain == "ai_assistant":
                raise NoStableComponentVersionError(f"{platform}/{data_domain}_{sub_domain}_export")
            suffix = f"{data_domain}_{sub_domain}_export" if sub_domain else f"{data_domain}_export"
            return {"component_name": f"{platform}/{suffix}"}

    monkeypatch.setattr(
        "backend.services.collection_config_execution.ComponentRuntimeResolver.from_async_session",
        lambda db: _FakeResolver(),
    )

    shop = (
        await config_execution_session.execute(
            select(ShopAccount).where(ShopAccount.shop_account_id == "shop-sg-1")
        )
    ).scalar_one()
    config_execution_session.add_all(
        [
            ShopAccountCapability(shop_account_id=shop.id, data_domain="products", enabled=True),
            ShopAccountCapability(shop_account_id=shop.id, data_domain="analytics", enabled=True),
        ]
    )
    await config_execution_session.commit()

    config = (
        await config_execution_session.execute(select(CollectionConfig).where(CollectionConfig.id == config_id))
    ).scalar_one()
    config.platform = "tiktok"
    await config_execution_session.commit()

    scope_result = await config_execution_session.execute(
        select(CollectionConfigShopScope).where(CollectionConfigShopScope.config_id == config_id)
    )
    scopes = scope_result.scalars().all()
    for scope in scopes:
        if scope.shop_account_id == "shop-sg-1":
            scope.data_domains = ["products", "analytics", "services"]
            scope.sub_domains = {"services": ["agent", "ai_assistant"]}
        else:
            scope.enabled = False
    await config_execution_session.commit()

    tasks = await create_tasks_for_config(
        config_execution_session,
        config_id=config_id,
        config_run_id=config_run_id,
        trigger_type="scheduled",
        resolve_runtime=True,
    )

    assert len(tasks) == 1
    task = tasks[0]
    assert task.account == "shop-sg-1"
    assert task.data_domains == ["products", "analytics", "services"]
    assert task.sub_domains == {"services": ["agent"]}
    assert task.total_domains == 3


@pytest.mark.asyncio
async def test_create_tasks_for_config_keeps_background_launch_disabled(
    config_execution_session,
    monkeypatch,
):
    config_id = await _seed_config(config_execution_session)
    config_run_id = await _seed_config_run(config_execution_session, config_id=config_id)

    class _FakeResolver:
        async def resolve_login_component(self, platform):
            return {"component_name": f"{platform}/login"}

        async def resolve_export_component(self, *, platform, data_domain, sub_domain):
            suffix = f"{data_domain}_{sub_domain}_export" if sub_domain else f"{data_domain}_export"
            return {"component_name": f"{platform}/{suffix}"}

    monkeypatch.setattr(
        "backend.services.collection_config_execution.ComponentRuntimeResolver.from_async_session",
        lambda db: _FakeResolver(),
    )

    scheduled_calls = []

    def _fake_create_task(coro):
        scheduled_calls.append(getattr(coro, "__name__", coro.__class__.__name__))
        coro.close()
        return SimpleNamespace(cancel=lambda: None)

    monkeypatch.setattr("asyncio.create_task", _fake_create_task)

    tasks = await create_tasks_for_config(
        config_execution_session,
        config_id=config_id,
        config_run_id=config_run_id,
        trigger_type="scheduled",
        start_background=True,
        resolve_runtime=True,
    )

    assert len(tasks) == 2
    assert scheduled_calls == []
    assert all(task.config_run_id == config_run_id for task in tasks)
