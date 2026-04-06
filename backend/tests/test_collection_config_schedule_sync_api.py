import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import (
    CollectionConfig,
    CollectionConfigShopScope,
    CollectionTask,
    MainAccount,
    ShopAccount,
    ShopAccountCapability,
)


class FakeScheduler:
    def __init__(self):
        self.jobs = {}
        self.add_calls = []
        self.remove_calls = []

    async def add_schedule(self, config_id: int, cron_expression: str):
        self.add_calls.append((config_id, cron_expression))
        self.jobs[config_id] = cron_expression
        return f"collection_config_{config_id}"

    async def remove_schedule(self, config_id: int):
        self.remove_calls.append(config_id)
        self.jobs.pop(config_id, None)
        return True

    def get_job_info(self, config_id: int):
        if config_id not in self.jobs:
            return None
        return {
            "job_id": f"collection_config_{config_id}",
            "next_run_time": "2026-04-07T06:00:00+08:00",
            "trigger": self.jobs[config_id],
        }


@pytest_asyncio.fixture
async def schedule_sync_engine():
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
def schedule_sync_session_factory(schedule_sync_engine):
    return async_sessionmaker(schedule_sync_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def schedule_sync_session(schedule_sync_session_factory):
    async with schedule_sync_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def schedule_sync_client(schedule_sync_session, monkeypatch):
    from backend.main import app
    from backend.models.database import get_async_db
    import backend.services.collection_scheduler as scheduler_module

    fake_scheduler = FakeScheduler()

    async def override_get_async_db():
        yield schedule_sync_session

    monkeypatch.setattr(scheduler_module, "APSCHEDULER_AVAILABLE", True)
    monkeypatch.setattr(scheduler_module.CollectionScheduler, "_instance", fake_scheduler)
    monkeypatch.setattr(scheduler_module.CollectionScheduler, "get_instance", classmethod(lambda cls, *args, **kwargs: fake_scheduler))
    monkeypatch.setattr(scheduler_module.CollectionScheduler, "validate_cron_expression", staticmethod(lambda expr: True))

    app.dependency_overrides[get_async_db] = override_get_async_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client, fake_scheduler
    app.dependency_overrides.pop(get_async_db, None)


async def _seed_shopee_accounts(session):
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

    capability_map = {shop.shop_account_id: shop.id for shop in shops}
    session.add_all(
        [
            ShopAccountCapability(shop_account_id=capability_map["shop-sg-1"], data_domain="orders", enabled=True),
            ShopAccountCapability(shop_account_id=capability_map["shop-my-1"], data_domain="products", enabled=True),
        ]
    )
    await session.commit()


@pytest.mark.asyncio
async def test_create_config_with_schedule_enabled_registers_job_immediately(
    schedule_sync_client,
    schedule_sync_session,
    auth_headers,
):
    client, fake_scheduler = schedule_sync_client
    await _seed_shopee_accounts(schedule_sync_session)

    response = await client.post(
        "/api/collection/configs",
        headers=auth_headers,
        json={
            "name": "shopee-scheduled-v1",
            "platform": "shopee",
            "shop_scopes": [
                {"shop_account_id": "shop-sg-1", "data_domains": ["orders"]},
                {"shop_account_id": "shop-my-1", "data_domains": ["products"]},
            ],
            "granularity": "daily",
            "time_selection": {"mode": "preset", "preset": "yesterday"},
            "schedule_enabled": True,
            "schedule_cron": "0 6 * * *",
            "retry_count": 3,
        },
    )

    assert response.status_code == 200
    config_id = response.json()["id"]
    assert fake_scheduler.add_calls == [(config_id, "0 6 * * *")]
    assert fake_scheduler.get_job_info(config_id)["job_id"] == f"collection_config_{config_id}"


@pytest.mark.asyncio
async def test_update_config_schedule_reschedules_immediately(
    schedule_sync_client,
    schedule_sync_session,
    auth_headers,
):
    client, fake_scheduler = schedule_sync_client
    await _seed_shopee_accounts(schedule_sync_session)

    create_response = await client.post(
        "/api/collection/configs",
        headers=auth_headers,
        json={
            "name": "shopee-scheduled-v2",
            "platform": "shopee",
            "shop_scopes": [
                {"shop_account_id": "shop-sg-1", "data_domains": ["orders"]},
                {"shop_account_id": "shop-my-1", "data_domains": ["products"]},
            ],
            "granularity": "daily",
            "time_selection": {"mode": "preset", "preset": "yesterday"},
            "schedule_enabled": False,
            "retry_count": 3,
        },
    )
    config_id = create_response.json()["id"]

    update_response = await client.put(
        f"/api/collection/configs/{config_id}",
        headers=auth_headers,
        json={
            "schedule_enabled": True,
            "schedule_cron": "0 12 * * *",
        },
    )

    assert update_response.status_code == 200
    assert fake_scheduler.add_calls[-1] == (config_id, "0 12 * * *")


@pytest.mark.asyncio
async def test_disable_and_delete_config_remove_registered_job_immediately(
    schedule_sync_client,
    schedule_sync_session,
    auth_headers,
):
    client, fake_scheduler = schedule_sync_client
    await _seed_shopee_accounts(schedule_sync_session)

    create_response = await client.post(
        "/api/collection/configs",
        headers=auth_headers,
        json={
            "name": "shopee-scheduled-v3",
            "platform": "shopee",
            "shop_scopes": [
                {"shop_account_id": "shop-sg-1", "data_domains": ["orders"]},
                {"shop_account_id": "shop-my-1", "data_domains": ["products"]},
            ],
            "granularity": "daily",
            "time_selection": {"mode": "preset", "preset": "yesterday"},
            "schedule_enabled": True,
            "schedule_cron": "0 6 * * *",
            "retry_count": 3,
        },
    )
    config_id = create_response.json()["id"]

    disable_response = await client.put(
        f"/api/collection/configs/{config_id}",
        headers=auth_headers,
        json={
            "schedule_enabled": False,
            "schedule_cron": None,
        },
    )
    assert disable_response.status_code == 200
    assert fake_scheduler.remove_calls[-1] == config_id

    delete_response = await client.delete(f"/api/collection/configs/{config_id}", headers=auth_headers)
    assert delete_response.status_code == 200
    assert fake_scheduler.remove_calls[-1] == config_id
