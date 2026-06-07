from datetime import date

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import (
    CollectionConfig,
    CollectionConfigShopScope,
    CollectionConfigTemplate,
    MainAccount,
    ShopAccount,
    ShopAccountCapability,
)


@pytest_asyncio.fixture
async def collection_template_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(MainAccount.__table__.create)
        await conn.run_sync(ShopAccount.__table__.create)
        await conn.run_sync(ShopAccountCapability.__table__.create)
        await conn.run_sync(CollectionConfigTemplate.__table__.create)
        await conn.run_sync(CollectionConfig.__table__.create)
        await conn.run_sync(CollectionConfigShopScope.__table__.create)

    yield engine
    await engine.dispose()


@pytest.fixture
def collection_template_session_factory(collection_template_engine):
    return async_sessionmaker(collection_template_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def collection_template_session(collection_template_session_factory):
    async with collection_template_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def collection_template_client(collection_template_session):
    from backend.dependencies.auth import get_current_user
    from backend.main import app
    from backend.models.database import get_async_db

    async def override_get_async_db():
        yield collection_template_session

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


async def _seed_template_accounts(session):
    session.add(
        MainAccount(
            platform="shopee",
            main_account_id="main-shopee",
            main_account_name="Shopee Main",
            username="main",
            password_encrypted="enc",
            enabled=True,
        )
    )
    await session.flush()

    shops = [
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
        ShopAccount(
            platform="shopee",
            shop_account_id="shop-ph-1",
            main_account_id="main-shopee",
            store_name="Shop PH 1",
            platform_shop_id="platform-ph-1",
            shop_region="PH",
            shop_type="local",
            enabled=True,
        ),
    ]
    session.add_all(shops)
    await session.flush()

    session.add_all(
        [
            ShopAccountCapability(shop_account_id=shops[0].id, data_domain="products", enabled=True),
            ShopAccountCapability(shop_account_id=shops[0].id, data_domain="services", enabled=True),
            ShopAccountCapability(shop_account_id=shops[1].id, data_domain="products", enabled=True),
            ShopAccountCapability(shop_account_id=shops[1].id, data_domain="services", enabled=True),
        ]
    )
    await session.commit()


@pytest.mark.asyncio
async def test_create_template_and_batch_returns_grouped_workbench_shape(
    collection_template_client,
    collection_template_session,
):
    await _seed_template_accounts(collection_template_session)

    template_response = await collection_template_client.post(
        "/api/collection/config-templates",
        json={
            "platform": "shopee",
            "main_account_id": "main-shopee",
            "granularity": "monthly",
            "default_date_range_type": "custom",
            "default_execution_mode": "headless",
            "default_shop_scopes": [
                {
                    "shop_account_id": "shop-my-1",
                    "data_domains": ["products", "services"],
                    "sub_domains": {"services": ["agent"]},
                    "enabled": True,
                },
                {
                    "shop_account_id": "shop-ph-1",
                    "data_domains": ["products", "services"],
                    "sub_domains": {"services": ["agent", "ai_assistant"]},
                    "enabled": True,
                },
            ],
        },
    )

    assert template_response.status_code == 200
    template_payload = template_response.json()
    assert template_payload["granularity"] == "monthly"
    assert template_payload["default_execution_mode"] == "headless"
    assert len(template_payload["default_shop_scopes"]) == 2

    batch_response = await collection_template_client.post(
        f"/api/collection/config-templates/{template_payload['id']}/batches",
        json={
            "batch_key": "2026-03",
            "time_selection": {
                "mode": "custom",
                "start_date": "2026-03-01",
                "end_date": "2026-03-31",
            },
            "shop_overrides": [
                {
                    "shop_account_id": "shop-ph-1",
                    "enabled": False,
                    "data_domains": [],
                    "sub_domains": {},
                }
            ],
        },
    )

    assert batch_response.status_code == 200
    batch_payload = batch_response.json()
    assert batch_payload["template_id"] == template_payload["id"]
    assert batch_payload["batch_key"] == "2026-03"
    assert batch_payload["status"] == "draft"
    assert batch_payload["shop_overrides"][0]["shop_account_id"] == "shop-ph-1"
    assert batch_payload["shop_scopes"][1]["enabled"] is False

    workbench_response = await collection_template_client.get(
        "/api/collection/config-templates",
        params={"platform": "shopee", "main_account_id": "main-shopee", "granularity": "monthly"},
    )
    assert workbench_response.status_code == 200
    workbench_payload = workbench_response.json()
    assert len(workbench_payload) == 1
    assert workbench_payload[0]["batches"][0]["batch_key"] == "2026-03"


@pytest.mark.asyncio
async def test_clone_next_batch_advances_month_and_keeps_overrides(
    collection_template_client,
    collection_template_session,
):
    await _seed_template_accounts(collection_template_session)

    template_response = await collection_template_client.post(
        "/api/collection/config-templates",
        json={
            "platform": "shopee",
            "main_account_id": "main-shopee",
            "granularity": "monthly",
            "default_date_range_type": "custom",
            "default_execution_mode": "headless",
            "default_shop_scopes": [
                {
                    "shop_account_id": "shop-my-1",
                    "data_domains": ["products", "services"],
                    "sub_domains": {"services": ["agent"]},
                    "enabled": True,
                },
                {
                    "shop_account_id": "shop-ph-1",
                    "data_domains": ["products", "services"],
                    "sub_domains": {"services": ["agent", "ai_assistant"]},
                    "enabled": True,
                },
            ],
        },
    )
    template_id = template_response.json()["id"]

    batch_response = await collection_template_client.post(
        f"/api/collection/config-templates/{template_id}/batches",
        json={
            "batch_key": "2026-03",
            "time_selection": {
                "mode": "custom",
                "start_date": "2026-03-01",
                "end_date": "2026-03-31",
            },
            "shop_overrides": [
                {
                    "shop_account_id": "shop-ph-1",
                    "enabled": False,
                    "data_domains": [],
                    "sub_domains": {},
                }
            ],
        },
    )
    config_id = batch_response.json()["id"]

    clone_response = await collection_template_client.post(
        f"/api/collection/config-batches/{config_id}/clone-next"
    )

    assert clone_response.status_code == 200
    payload = clone_response.json()
    assert payload["batch_key"] == "2026-04"
    assert payload["custom_date_start"] == "2026-04-01"
    assert payload["custom_date_end"] == "2026-04-30"
    assert payload["shop_overrides"][0]["shop_account_id"] == "shop-ph-1"
    assert payload["shop_scopes"][1]["enabled"] is False


@pytest.mark.asyncio
async def test_advance_current_config_updates_same_record_window(
    collection_template_client,
    collection_template_session,
):
    await _seed_template_accounts(collection_template_session)

    template_response = await collection_template_client.post(
        "/api/collection/config-templates",
        json={
            "platform": "shopee",
            "main_account_id": "main-shopee",
            "granularity": "monthly",
            "default_date_range_type": "custom",
            "default_execution_mode": "headless",
            "default_shop_scopes": [
                {
                    "shop_account_id": "shop-my-1",
                    "data_domains": ["products"],
                    "enabled": True,
                }
            ],
        },
    )
    template_id = template_response.json()["id"]

    batch_response = await collection_template_client.post(
        f"/api/collection/config-templates/{template_id}/batches",
        json={
            "batch_key": "2026-06",
            "time_selection": {
                "mode": "custom",
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
            },
            "status": "active",
        },
    )
    config_id = batch_response.json()["id"]

    response = await collection_template_client.post(f"/api/collection/configs/{config_id}/advance-current")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == config_id
    assert payload["batch_key"] == "2026-07"
    assert payload["custom_date_start"] == "2026-07-01"
    assert payload["custom_date_end"] == "2026-07-31"


@pytest.mark.asyncio
async def test_bulk_advance_current_granularity_updates_matching_configs(
    collection_template_client,
    collection_template_session,
):
    await _seed_template_accounts(collection_template_session)

    template_response = await collection_template_client.post(
        "/api/collection/config-templates",
        json={
            "platform": "shopee",
            "main_account_id": "main-shopee",
            "granularity": "weekly",
            "default_date_range_type": "custom",
            "default_execution_mode": "headless",
            "default_shop_scopes": [
                {
                    "shop_account_id": "shop-my-1",
                    "data_domains": ["products"],
                    "enabled": True,
                }
            ],
        },
    )
    template_id = template_response.json()["id"]

    batch_response = await collection_template_client.post(
        f"/api/collection/config-templates/{template_id}/batches",
        json={
            "batch_key": "2026-W23",
            "time_selection": {
                "mode": "custom",
                "start_date": "2026-06-01",
                "end_date": "2026-06-07",
            },
            "status": "active",
        },
    )
    config_id = batch_response.json()["id"]

    response = await collection_template_client.post(
        "/api/collection/configs/advance-current-granularity",
        json={"granularity": "weekly", "platform": "shopee"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["affected_config_ids"] == [config_id]

    refreshed = await collection_template_client.get(
        "/api/collection/config-templates",
        params={"platform": "shopee", "main_account_id": "main-shopee", "granularity": "weekly"},
    )
    batch_payload = refreshed.json()[0]["batches"][0]
    assert batch_payload["batch_key"] == "2026-W24"
    assert batch_payload["custom_date_start"] == "2026-06-08"
    assert batch_payload["custom_date_end"] == "2026-06-14"


@pytest.mark.asyncio
async def test_update_batch_persists_batch_metadata_and_scope_changes(
    collection_template_client,
    collection_template_session,
):
    await _seed_template_accounts(collection_template_session)

    template_response = await collection_template_client.post(
        "/api/collection/config-templates",
        json={
            "platform": "shopee",
            "main_account_id": "main-shopee",
            "granularity": "weekly",
            "default_date_range_type": "custom",
            "default_execution_mode": "headless",
            "default_shop_scopes": [
                {
                    "shop_account_id": "shop-my-1",
                    "data_domains": ["products", "services"],
                    "sub_domains": {"services": ["agent"]},
                    "enabled": True,
                },
                {
                    "shop_account_id": "shop-ph-1",
                    "data_domains": ["products", "services"],
                    "sub_domains": {"services": ["agent", "ai_assistant"]},
                    "enabled": True,
                },
            ],
        },
    )
    template_id = template_response.json()["id"]

    batch_response = await collection_template_client.post(
        f"/api/collection/config-templates/{template_id}/batches",
        json={
            "batch_key": "2026-W23",
            "time_selection": {
                "mode": "custom",
                "start_date": "2026-06-01",
                "end_date": "2026-06-07",
            },
            "status": "draft",
            "note": "initial note",
            "shop_overrides": [],
        },
    )
    batch_id = batch_response.json()["id"]

    update_response = await collection_template_client.put(
        f"/api/collection/configs/{batch_id}",
        json={
            "batch_key": "2026-W24",
            "batch_status": "active",
            "batch_note": "updated note",
            "shop_scopes": [
                {
                    "shop_account_id": "shop-my-1",
                    "data_domains": ["products"],
                    "sub_domains": {},
                    "enabled": True,
                },
                {
                    "shop_account_id": "shop-ph-1",
                    "data_domains": ["products", "services"],
                    "sub_domains": {"services": ["agent"]},
                    "enabled": True,
                },
            ],
            "time_selection": {
                "mode": "custom",
                "start_date": "2026-06-08",
                "end_date": "2026-06-14",
            },
        },
    )

    assert update_response.status_code == 200

    list_response = await collection_template_client.get(
        "/api/collection/config-templates",
        params={"platform": "shopee", "main_account_id": "main-shopee", "granularity": "weekly"},
    )
    payload = list_response.json()
    batch = payload[0]["batches"][0]
    assert batch["batch_key"] == "2026-W24"
    assert batch["status"] == "active"
    assert batch["note"] == "updated note"
    assert batch["custom_date_start"] == "2026-06-08"
    assert batch["custom_date_end"] == "2026-06-14"
    assert batch["shop_overrides"][0]["shop_account_id"] == "shop-my-1"


@pytest.mark.asyncio
async def test_template_update_does_not_implicitly_mutate_existing_batches(
    collection_template_client,
    collection_template_session,
):
    await _seed_template_accounts(collection_template_session)

    template_response = await collection_template_client.post(
        "/api/collection/config-templates",
        json={
            "platform": "shopee",
            "main_account_id": "main-shopee",
            "granularity": "monthly",
            "default_date_range_type": "custom",
            "default_execution_mode": "headless",
            "default_shop_scopes": [
                {
                    "shop_account_id": "shop-my-1",
                    "data_domains": ["products", "services"],
                    "sub_domains": {"services": ["agent"]},
                    "enabled": True,
                },
                {
                    "shop_account_id": "shop-ph-1",
                    "data_domains": ["products", "services"],
                    "sub_domains": {"services": ["agent", "ai_assistant"]},
                    "enabled": True,
                },
            ],
        },
    )
    template_id = template_response.json()["id"]

    batch_response = await collection_template_client.post(
        f"/api/collection/config-templates/{template_id}/batches",
        json={
            "batch_key": "2026-03",
            "time_selection": {
                "mode": "custom",
                "start_date": "2026-03-01",
                "end_date": "2026-03-31",
            },
            "shop_overrides": [],
        },
    )
    batch_id = batch_response.json()["id"]

    update_template_response = await collection_template_client.put(
        f"/api/collection/config-templates/{template_id}",
        json={
            "default_shop_scopes": [
                {
                    "shop_account_id": "shop-my-1",
                    "data_domains": ["products"],
                    "sub_domains": {},
                    "enabled": True,
                },
                {
                    "shop_account_id": "shop-ph-1",
                    "data_domains": ["products"],
                    "sub_domains": {},
                    "enabled": True,
                },
            ]
        },
    )
    assert update_template_response.status_code == 200

    batch_detail_response = await collection_template_client.get(f"/api/collection/configs/{batch_id}")
    assert batch_detail_response.status_code == 200
    scopes = batch_detail_response.json()["shop_scopes"]
    assert scopes[0]["data_domains"] == ["products", "services"]
    assert scopes[1]["data_domains"] == ["products", "services"]


@pytest.mark.asyncio
async def test_reapply_template_defaults_rebases_batch_but_preserves_exceptions(
    collection_template_client,
    collection_template_session,
):
    await _seed_template_accounts(collection_template_session)

    template_response = await collection_template_client.post(
        "/api/collection/config-templates",
        json={
            "platform": "shopee",
            "main_account_id": "main-shopee",
            "granularity": "monthly",
            "default_date_range_type": "custom",
            "default_execution_mode": "headless",
            "default_shop_scopes": [
                {
                    "shop_account_id": "shop-my-1",
                    "data_domains": ["products", "services"],
                    "sub_domains": {"services": ["agent"]},
                    "enabled": True,
                },
                {
                    "shop_account_id": "shop-ph-1",
                    "data_domains": ["products", "services"],
                    "sub_domains": {"services": ["agent", "ai_assistant"]},
                    "enabled": True,
                },
            ],
        },
    )
    template_id = template_response.json()["id"]

    batch_response = await collection_template_client.post(
        f"/api/collection/config-templates/{template_id}/batches",
        json={
            "batch_key": "2026-03",
            "time_selection": {
                "mode": "custom",
                "start_date": "2026-03-01",
                "end_date": "2026-03-31",
            },
            "shop_overrides": [
                {
                    "shop_account_id": "shop-ph-1",
                    "enabled": False,
                    "data_domains": [],
                    "sub_domains": {},
                }
            ],
        },
    )
    batch_id = batch_response.json()["id"]

    update_template_response = await collection_template_client.put(
        f"/api/collection/config-templates/{template_id}",
        json={
            "default_shop_scopes": [
                {
                    "shop_account_id": "shop-my-1",
                    "data_domains": ["products"],
                    "sub_domains": {},
                    "enabled": True,
                },
                {
                    "shop_account_id": "shop-ph-1",
                    "data_domains": ["products"],
                    "sub_domains": {},
                    "enabled": True,
                },
            ]
        },
    )
    assert update_template_response.status_code == 200

    reapply_response = await collection_template_client.post(
        f"/api/collection/config-batches/{batch_id}/reapply-template"
    )
    assert reapply_response.status_code == 200
    payload = reapply_response.json()
    my_scope = next(scope for scope in payload["shop_scopes"] if scope["shop_account_id"] == "shop-my-1")
    ph_scope = next(scope for scope in payload["shop_scopes"] if scope["shop_account_id"] == "shop-ph-1")
    assert my_scope["data_domains"] == ["products"]
    assert ph_scope["enabled"] is False
    assert payload["shop_overrides"][0]["shop_account_id"] == "shop-ph-1"


@pytest.mark.asyncio
async def test_template_summary_reports_missing_and_stale_shop_scope_drift(
    collection_template_client,
    collection_template_session,
):
    await _seed_template_accounts(collection_template_session)

    template_response = await collection_template_client.post(
        "/api/collection/config-templates",
        json={
            "platform": "shopee",
            "main_account_id": "main-shopee",
            "granularity": "monthly",
            "default_date_range_type": "custom",
            "default_execution_mode": "headless",
            "default_shop_scopes": [
                {
                    "shop_account_id": "shop-my-1",
                    "data_domains": ["products"],
                    "sub_domains": {},
                    "enabled": True,
                },
            ],
        },
    )
    assert template_response.status_code == 200
    template_id = template_response.json()["id"]

    from sqlalchemy import select
    from modules.core.db import CollectionConfigTemplate, ShopAccount

    template = await collection_template_session.get(CollectionConfigTemplate, template_id)
    template.default_shop_scopes = [
        {
            "shop_account_id": "shop-my-1",
            "data_domains": ["products"],
            "sub_domains": {},
            "enabled": True,
        },
        {
            "shop_account_id": "shop-ph-1",
            "data_domains": ["products"],
            "sub_domains": {},
            "enabled": True,
        },
    ]
    stale_shop = (
        await collection_template_session.execute(
            select(ShopAccount).where(ShopAccount.shop_account_id == "shop-ph-1")
        )
    ).scalar_one()
    stale_shop.enabled = False

    collection_template_session.add(
        ShopAccount(
            platform="shopee",
            shop_account_id="shop-new-1",
            main_account_id="main-shopee",
            store_name="Shop New 1",
            platform_shop_id="platform-new-1",
            shop_region="SG",
            shop_type="local",
            enabled=True,
        )
    )
    await collection_template_session.commit()

    list_response = await collection_template_client.get(
        "/api/collection/config-templates",
        params={"platform": "shopee", "main_account_id": "main-shopee", "granularity": "monthly"},
    )

    assert list_response.status_code == 200
    payload = list_response.json()[0]
    assert payload["active_shop_count"] == 2
    assert payload["template_shop_count"] == 2
    assert payload["missing_shop_scope_ids"] == ["shop-new-1"]
    assert payload["stale_shop_scope_ids"] == ["shop-ph-1"]


@pytest.mark.asyncio
async def test_batch_summary_reports_template_scope_sync_drift(
    collection_template_client,
    collection_template_session,
):
    await _seed_template_accounts(collection_template_session)

    template_response = await collection_template_client.post(
        "/api/collection/config-templates",
        json={
            "platform": "shopee",
            "main_account_id": "main-shopee",
            "granularity": "monthly",
            "default_date_range_type": "custom",
            "default_execution_mode": "headless",
            "default_shop_scopes": [
                {
                    "shop_account_id": "shop-my-1",
                    "data_domains": ["products"],
                    "sub_domains": {},
                    "enabled": True,
                },
                {
                    "shop_account_id": "shop-ph-1",
                    "data_domains": ["products"],
                    "sub_domains": {},
                    "enabled": True,
                },
            ],
        },
    )
    template_id = template_response.json()["id"]

    batch_response = await collection_template_client.post(
        f"/api/collection/config-templates/{template_id}/batches",
        json={
            "batch_key": "2026-03",
            "time_selection": {
                "mode": "custom",
                "start_date": "2026-03-01",
                "end_date": "2026-03-31",
            },
            "shop_overrides": [],
        },
    )
    assert batch_response.status_code == 200

    update_template_response = await collection_template_client.put(
        f"/api/collection/config-templates/{template_id}",
        json={
            "default_shop_scopes": [
                {
                    "shop_account_id": "shop-my-1",
                    "data_domains": ["products"],
                    "sub_domains": {},
                    "enabled": True,
                },
                {
                    "shop_account_id": "shop-new-2",
                    "data_domains": ["products"],
                    "sub_domains": {},
                    "enabled": True,
                },
            ]
        },
    )
    assert update_template_response.status_code == 400

    from modules.core.db import ShopAccount

    collection_template_session.add(
        ShopAccount(
            platform="shopee",
            shop_account_id="shop-new-2",
            main_account_id="main-shopee",
            store_name="Shop New 2",
            platform_shop_id="platform-new-2",
            shop_region="MY",
            shop_type="local",
            enabled=True,
        )
    )
    await collection_template_session.commit()

    update_template_response = await collection_template_client.put(
        f"/api/collection/config-templates/{template_id}",
        json={
            "default_shop_scopes": [
                {
                    "shop_account_id": "shop-my-1",
                    "data_domains": ["products"],
                    "sub_domains": {},
                    "enabled": True,
                },
                {
                    "shop_account_id": "shop-new-2",
                    "data_domains": ["products"],
                    "sub_domains": {},
                    "enabled": True,
                },
            ]
        },
    )
    assert update_template_response.status_code == 200

    list_response = await collection_template_client.get(
        "/api/collection/config-templates",
        params={"platform": "shopee", "main_account_id": "main-shopee", "granularity": "monthly"},
    )
    payload = list_response.json()[0]["batches"][0]
    assert payload["missing_template_shop_scope_ids"] == ["shop-new-2"]
    assert payload["stale_template_shop_scope_ids"] == ["shop-ph-1"]


@pytest.mark.asyncio
async def test_create_future_batches_creates_multiple_months_and_skips_existing(
    collection_template_client,
    collection_template_session,
):
    await _seed_template_accounts(collection_template_session)

    template_response = await collection_template_client.post(
        "/api/collection/config-templates",
        json={
            "platform": "shopee",
            "main_account_id": "main-shopee",
            "granularity": "monthly",
            "default_date_range_type": "custom",
            "default_execution_mode": "headless",
            "default_shop_scopes": [
                {
                    "shop_account_id": "shop-my-1",
                    "data_domains": ["products"],
                    "sub_domains": {},
                    "enabled": True,
                },
                {
                    "shop_account_id": "shop-ph-1",
                    "data_domains": ["products"],
                    "sub_domains": {},
                    "enabled": True,
                },
            ],
        },
    )
    template_id = template_response.json()["id"]

    seed_batch_response = await collection_template_client.post(
        f"/api/collection/config-templates/{template_id}/batches",
        json={
            "batch_key": "2026-03",
            "time_selection": {
                "mode": "custom",
                "start_date": "2026-03-01",
                "end_date": "2026-03-31",
            },
            "shop_overrides": [],
        },
    )
    seed_batch_id = seed_batch_response.json()["id"]

    future_response = await collection_template_client.post(
        f"/api/collection/config-batches/{seed_batch_id}/create-future-batches",
        json={"periods": 3},
    )
    assert future_response.status_code == 200
    payload = future_response.json()
    assert [item["batch_key"] for item in payload["created_batches"]] == ["2026-04", "2026-05", "2026-06"]
    assert payload["skipped_batch_keys"] == []

    repeat_response = await collection_template_client.post(
        f"/api/collection/config-batches/{seed_batch_id}/create-future-batches",
        json={"periods": 3},
    )
    assert repeat_response.status_code == 200
    repeat_payload = repeat_response.json()
    assert repeat_payload["created_batches"] == []
    assert repeat_payload["skipped_batch_keys"] == ["2026-04", "2026-05", "2026-06"]


@pytest.mark.asyncio
async def test_backfill_legacy_configs_creates_templates_and_assigns_batches(
    collection_template_client,
    collection_template_session,
):
    await _seed_template_accounts(collection_template_session)

    legacy_config = CollectionConfig(
        name="legacy-monthly-config",
        platform="shopee",
        main_account_id="main-shopee",
        account_ids=["shop-my-1", "shop-ph-1"],
        data_domains=["products", "services"],
        sub_domains={"services": ["agent"]},
        granularity="monthly",
        date_range_type="custom",
        custom_date_start=date(2026, 3, 1),
        custom_date_end=date(2026, 3, 31),
        execution_mode="headless",
        schedule_enabled=False,
        schedule_cron=None,
        retry_count=3,
        is_active=True,
    )
    collection_template_session.add(legacy_config)
    await collection_template_session.flush()
    collection_template_session.add_all(
        [
            CollectionConfigShopScope(
                config_id=legacy_config.id,
                shop_account_id="shop-my-1",
                data_domains=["products"],
                sub_domains={},
                enabled=True,
            ),
            CollectionConfigShopScope(
                config_id=legacy_config.id,
                shop_account_id="shop-ph-1",
                data_domains=["products", "services"],
                sub_domains={"services": ["agent"]},
                enabled=True,
            ),
        ]
    )
    await collection_template_session.commit()

    response = await collection_template_client.post("/api/collection/config-template-backfill")
    assert response.status_code == 200
    payload = response.json()
    assert payload["created_template_count"] == 1
    assert payload["attached_batch_count"] == 1
    assert payload["skipped_config_ids"] == []

    workbench_response = await collection_template_client.get(
        "/api/collection/config-templates",
        params={"platform": "shopee", "main_account_id": "main-shopee", "granularity": "monthly"},
    )
    assert workbench_response.status_code == 200
    template = workbench_response.json()[0]
    assert template["batch_count"] == 1
    assert template["batches"][0]["batch_key"] == "2026-03"
