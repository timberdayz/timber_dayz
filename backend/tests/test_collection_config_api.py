import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import (
    CollectionConfig,
    CollectionConfigShopScope,
    MainAccount,
    ShopAccount,
    ShopAccountCapability,
)


@pytest_asyncio.fixture
async def collection_config_sqlite_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(MainAccount.__table__.create)
        await conn.run_sync(ShopAccount.__table__.create)
        await conn.run_sync(ShopAccountCapability.__table__.create)
        await conn.run_sync(CollectionConfig.__table__.create)
        await conn.run_sync(CollectionConfigShopScope.__table__.create)

    yield engine
    await engine.dispose()


@pytest.fixture
def collection_config_session_factory(collection_config_sqlite_engine):
    return async_sessionmaker(collection_config_sqlite_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def collection_config_sqlite_session(collection_config_session_factory):
    async with collection_config_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def collection_config_async_client(collection_config_sqlite_session):
    from backend.main import app
    from backend.dependencies.auth import get_current_user
    from backend.models.database import get_async_db

    async def override_get_async_db():
        yield collection_config_sqlite_session

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
            ShopAccountCapability(
                shop_account_id=capability_map["shop-sg-1"],
                data_domain="orders",
                enabled=True,
            ),
            ShopAccountCapability(
                shop_account_id=capability_map["shop-sg-1"],
                data_domain="services",
                enabled=True,
            ),
            ShopAccountCapability(
                shop_account_id=capability_map["shop-my-1"],
                data_domain="products",
                enabled=True,
            ),
            ShopAccountCapability(
                shop_account_id=capability_map["shop-my-1"],
                data_domain="services",
                enabled=True,
            ),
        ]
    )
    await session.commit()


def test_build_collection_config_record_sets_explicit_timestamps():
    from backend.routers.collection_config import _build_collection_config_record
    from backend.schemas.collection import (
        CollectionConfigCreate,
        CollectionConfigShopScopePayload,
        TimeSelectionPayload,
    )

    record = _build_collection_config_record(
        config_name="shopee-shop-scope-v1",
        config=CollectionConfigCreate(
            name="shopee-shop-scope-v1",
            platform="shopee",
            main_account_id="main-shopee",
            shop_scopes=[
                CollectionConfigShopScopePayload(
                    shop_account_id="shop-sg-1",
                    data_domains=["orders", "services"],
                    sub_domains={"services": ["agent"]},
                ),
                CollectionConfigShopScopePayload(
                    shop_account_id="shop-my-1",
                    data_domains=["products"],
                ),
            ],
            granularity="weekly",
            time_selection=TimeSelectionPayload(mode="preset", preset="last_7_days"),
            schedule_enabled=False,
            retry_count=3,
        ),
    )

    assert record.created_at is not None
    assert record.updated_at is not None
    assert record.account_ids == ["shop-sg-1", "shop-my-1"]
    assert record.data_domains == ["orders", "services", "products"]
    assert record.sub_domains == {"services": ["agent"]}


def test_build_collection_config_record_defaults_execution_mode_to_headless():
    from backend.routers.collection_config import _build_collection_config_record
    from backend.schemas.collection import (
        CollectionConfigCreate,
        CollectionConfigShopScopePayload,
        TimeSelectionPayload,
    )

    record = _build_collection_config_record(
        config_name="shopee-shop-scope-v2",
        config=CollectionConfigCreate(
            name="shopee-shop-scope-v2",
            platform="shopee",
            main_account_id="main-shopee",
            shop_scopes=[
                CollectionConfigShopScopePayload(
                    shop_account_id="shop-sg-1",
                    data_domains=["orders"],
                )
            ],
            granularity="daily",
            time_selection=TimeSelectionPayload(mode="preset", preset="yesterday"),
            schedule_enabled=False,
            retry_count=3,
        ),
    )

    assert record.execution_mode == "headless"


@pytest.mark.asyncio
async def test_create_config_persists_shop_scopes_and_time_selection(
    collection_config_async_client,
    collection_config_sqlite_session,
):
    await _seed_shopee_accounts(collection_config_sqlite_session)

    response = await collection_config_async_client.post(
        "/api/collection/configs",
        json={
            "name": "shopee-daily-shop-scope-v1",
            "platform": "shopee",
            "main_account_id": "main-shopee",
            "shop_scopes": [
                {
                    "shop_account_id": "shop-sg-1",
                    "data_domains": ["orders", "services"],
                    "sub_domains": {"services": ["agent", "invalid"]},
                },
                {
                    "shop_account_id": "shop-my-1",
                    "data_domains": ["products", "services"],
                    "sub_domains": {"services": ["agent"]},
                },
            ],
            "granularity": "daily",
            "time_selection": {
                "mode": "preset",
                "preset": "last_7_days",
            },
            "schedule_enabled": False,
            "retry_count": 3,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["platform"] == "shopee"
    assert payload["granularity"] == "weekly"
    assert payload["date_range_type"] == "last_7_days"
    assert set(payload["account_ids"]) == {"shop-my-1", "shop-sg-1"}
    assert payload["data_domains"] == ["orders", "services", "products"]
    assert len(payload["shop_scopes"]) == 2
    assert payload["shop_scopes"][0]["shop_account_id"] == "shop-my-1"
    assert payload["shop_scopes"][1]["shop_account_id"] == "shop-sg-1"
    assert payload["shop_scopes"][1]["sub_domains"] == {"services": ["agent"]}


@pytest.mark.asyncio
async def test_create_config_requires_all_active_shop_scopes(
    collection_config_async_client,
    collection_config_sqlite_session,
):
    await _seed_shopee_accounts(collection_config_sqlite_session)

    response = await collection_config_async_client.post(
        "/api/collection/configs",
        json={
            "name": "shopee-invalid-v1",
            "platform": "shopee",
            "main_account_id": "main-shopee",
            "shop_scopes": [
                {
                    "shop_account_id": "shop-sg-1",
                    "data_domains": ["orders"],
                }
            ],
            "granularity": "daily",
            "time_selection": {
                "mode": "preset",
                "preset": "yesterday",
            },
            "schedule_enabled": False,
            "retry_count": 3,
        },
    )

    assert response.status_code == 400
    assert "missing active shop scopes" in str(response.json())


@pytest.mark.asyncio
async def test_update_config_replaces_shop_scopes_and_normalizes_custom_time_selection(
    collection_config_async_client,
    collection_config_sqlite_session,
):
    await _seed_shopee_accounts(collection_config_sqlite_session)

    config = CollectionConfig(
        name="shopee-services-v1",
        platform="shopee",
        main_account_id="main-shopee",
        account_ids=["shop-sg-1", "shop-my-1"],
        data_domains=["services"],
        sub_domains={"services": ["agent"]},
        granularity="daily",
        date_range_type="yesterday",
        custom_date_start=None,
        custom_date_end=None,
        schedule_enabled=False,
        schedule_cron=None,
        retry_count=3,
        is_active=True,
        execution_mode="headless",
    )
    collection_config_sqlite_session.add(config)
    await collection_config_sqlite_session.flush()
    collection_config_sqlite_session.add_all(
        [
            CollectionConfigShopScope(
                config_id=config.id,
                shop_account_id="shop-sg-1",
                data_domains=["services"],
                sub_domains={"services": ["agent"]},
                enabled=True,
            ),
            CollectionConfigShopScope(
                config_id=config.id,
                shop_account_id="shop-my-1",
                data_domains=["services"],
                sub_domains={"services": ["agent"]},
                enabled=True,
            ),
        ]
    )
    await collection_config_sqlite_session.commit()
    await collection_config_sqlite_session.refresh(config)

    response = await collection_config_async_client.put(
        f"/api/collection/configs/{config.id}",
        json={
            "shop_scopes": [
                {
                    "shop_account_id": "shop-sg-1",
                    "data_domains": ["orders", "services"],
                    "sub_domains": {"services": ["agent", "invalid"]},
                },
                {
                    "shop_account_id": "shop-my-1",
                    "data_domains": ["products"],
                },
            ],
            "execution_mode": "headed",
            "time_selection": {
                "mode": "custom",
                "start_date": "2026-03-01",
                "end_date": "2026-03-31",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_mode"] == "headed"
    assert payload["granularity"] == "daily"
    assert payload["date_range_type"] == "custom"
    assert payload["custom_date_start"] == "2026-03-01"
    assert payload["custom_date_end"] == "2026-03-31"
    assert payload["shop_scopes"][0]["shop_account_id"] == "shop-my-1"
    assert payload["shop_scopes"][0]["data_domains"] == ["products"]
    assert payload["shop_scopes"][1]["shop_account_id"] == "shop-sg-1"
    assert payload["shop_scopes"][1]["sub_domains"] == {"services": ["agent"]}
