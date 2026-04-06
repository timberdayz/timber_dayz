import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import (
    CollectionConfig,
    CollectionConfigShopScope,
    MainAccount,
    ShopAccount,
    ShopAccountCapability,
)


@pytest_asyncio.fixture
async def collection_config_main_account_engine():
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
def collection_config_main_account_session_factory(collection_config_main_account_engine):
    return async_sessionmaker(collection_config_main_account_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def collection_config_main_account_session(collection_config_main_account_session_factory):
    async with collection_config_main_account_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def collection_config_main_account_async_client(collection_config_main_account_session):
    from backend.main import app
    from backend.dependencies.auth import get_current_user
    from backend.models.database import get_async_db

    async def override_get_async_db():
        yield collection_config_main_account_session

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


@pytest.mark.asyncio
async def test_collection_config_model_requires_main_account_id_column():
    assert "main_account_id" in CollectionConfig.__table__.c


@pytest.mark.asyncio
async def test_collection_config_allows_same_name_for_different_main_accounts(
    collection_config_main_account_session_factory,
):
    async with collection_config_main_account_session_factory() as session:
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
                    enabled=True,
                ),
            ]
        )
        await session.flush()

        session.add(
            CollectionConfig(
                name="shopee-main-scope-v1",
                platform="shopee",
                main_account_id="main-shopee-a",
                account_ids=["shop-a-1"],
                data_domains=["orders"],
                sub_domains=None,
                granularity="daily",
                date_range_type="yesterday",
                execution_mode="headless",
                schedule_enabled=False,
                schedule_cron=None,
                retry_count=3,
                is_active=True,
            )
        )
        session.add(
            CollectionConfig(
                name="shopee-main-scope-v1",
                platform="shopee",
                main_account_id="main-shopee-b",
                account_ids=["shop-b-1"],
                data_domains=["orders"],
                sub_domains=None,
                granularity="daily",
                date_range_type="yesterday",
                execution_mode="headless",
                schedule_enabled=False,
                schedule_cron=None,
                retry_count=3,
                is_active=True,
            )
        )

        try:
            await session.commit()
        except IntegrityError as exc:  # pragma: no cover - current failure path before implementation
            pytest.fail(f"configs should be unique per platform + main_account_id + name: {exc}")


async def _seed_multi_main_accounts(session):
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
                enabled=True,
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
            shop_account_id="shop-a-2",
            main_account_id="main-shopee-a",
            store_name="Shop A 2",
            platform_shop_id="platform-a-2",
            shop_region="MY",
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

    capability_rows = []
    for shop in shops:
        capability_rows.append(
            ShopAccountCapability(
                shop_account_id=shop.id,
                data_domain="orders",
                enabled=True,
            )
        )
    session.add_all(capability_rows)
    await session.commit()


@pytest.mark.asyncio
async def test_create_config_requires_main_account_id(
    collection_config_main_account_async_client,
    collection_config_main_account_session,
):
    await _seed_multi_main_accounts(collection_config_main_account_session)

    response = await collection_config_main_account_async_client.post(
        "/api/collection/configs",
        json={
            "name": "missing-main-account-v1",
            "platform": "shopee",
            "shop_scopes": [
                {
                    "shop_account_id": "shop-a-1",
                    "data_domains": ["orders"],
                },
                {
                    "shop_account_id": "shop-a-2",
                    "data_domains": ["orders"],
                },
                {
                    "shop_account_id": "shop-b-1",
                    "data_domains": ["orders"],
                },
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

    assert response.status_code == 422
    assert "main_account_id" in response.text


@pytest.mark.asyncio
async def test_create_config_rejects_shop_scopes_from_other_main_account(
    collection_config_main_account_async_client,
    collection_config_main_account_session,
):
    await _seed_multi_main_accounts(collection_config_main_account_session)

    response = await collection_config_main_account_async_client.post(
        "/api/collection/configs",
        json={
            "name": "mixed-main-accounts-v1",
            "platform": "shopee",
            "main_account_id": "main-shopee-a",
            "shop_scopes": [
                {
                    "shop_account_id": "shop-a-1",
                    "data_domains": ["orders"],
                },
                {
                    "shop_account_id": "shop-a-2",
                    "data_domains": ["orders"],
                },
                {
                    "shop_account_id": "shop-b-1",
                    "data_domains": ["orders"],
                },
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
    assert "main account" in response.text.lower()


@pytest.mark.asyncio
async def test_list_configs_filters_by_main_account_and_runtime_fields(
    collection_config_main_account_async_client,
    collection_config_main_account_session,
):
    await _seed_multi_main_accounts(collection_config_main_account_session)
    collection_config_main_account_session.add_all(
        [
            CollectionConfig(
                name="scope-a-daily-v1",
                platform="shopee",
                main_account_id="main-shopee-a",
                account_ids=["shop-a-1", "shop-a-2"],
                data_domains=["orders"],
                sub_domains=None,
                granularity="daily",
                date_range_type="yesterday",
                execution_mode="headless",
                schedule_enabled=False,
                schedule_cron=None,
                retry_count=3,
                is_active=True,
            ),
            CollectionConfig(
                name="scope-b-weekly-v1",
                platform="shopee",
                main_account_id="main-shopee-b",
                account_ids=["shop-b-1"],
                data_domains=["orders"],
                sub_domains=None,
                granularity="weekly",
                date_range_type="last_7_days",
                execution_mode="headed",
                schedule_enabled=True,
                schedule_cron="0 6 * * *",
                retry_count=3,
                is_active=True,
            ),
        ]
    )
    await collection_config_main_account_session.commit()

    response = await collection_config_main_account_async_client.get(
        "/api/collection/configs",
        params={
            "platform": "shopee",
            "main_account_id": "main-shopee-b",
            "date_range_type": "last_7_days",
            "execution_mode": "headed",
            "schedule_enabled": "true",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["name"] == "scope-b-weekly-v1"
    assert payload[0]["main_account_id"] == "main-shopee-b"


@pytest.mark.asyncio
async def test_config_coverage_filters_by_main_account(
    collection_config_main_account_async_client,
    collection_config_main_account_session,
):
    await _seed_multi_main_accounts(collection_config_main_account_session)

    response = await collection_config_main_account_async_client.get(
        "/api/collection/config-coverage",
        params={
            "platform": "shopee",
            "main_account_id": "main-shopee-a",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert {item["main_account_id"] for item in payload["items"]} == {"main-shopee-a"}
