import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import Base, CollectionConfig


@pytest_asyncio.fixture
async def collection_config_sqlite_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(Base.metadata.create_all)

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
    from backend.models.database import get_async_db

    async def override_get_async_db():
        yield collection_config_sqlite_session

    app.dependency_overrides[get_async_db] = override_get_async_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client
    app.dependency_overrides.pop(get_async_db, None)


def test_build_collection_config_record_sets_explicit_timestamps():
    from backend.routers.collection_config import _build_collection_config_record
    from backend.schemas.collection import CollectionConfigCreate, TimeSelectionPayload

    record = _build_collection_config_record(
        config_name="miaoshou-orders-v1",
        config=CollectionConfigCreate(
            name="miaoshou-orders-v1",
            platform="miaoshou",
            account_ids=["miaoshou_real_001"],
            data_domains=["orders"],
            sub_domains={"orders": ["shopee", "tiktok"]},
            granularity="weekly",
            time_selection=TimeSelectionPayload(mode="preset", preset="last_7_days"),
            schedule_enabled=False,
            retry_count=3,
        ),
    )

    assert record.created_at is not None
    assert record.updated_at is not None


@pytest.mark.asyncio
async def test_create_config_normalizes_time_selection_and_sub_domains(collection_config_async_client):
    response = await collection_config_async_client.post(
        "/api/collection/configs",
        json={
            "name": None,
            "platform": "shopee",
            "account_ids": [],
            "data_domains": ["orders", "services"],
            "sub_domains": {
                "services": ["agent", "invalid"],
            },
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
    assert payload["account_ids"] == []
    assert payload["data_domains"] == ["orders", "services"]
    assert payload["sub_domains"] == {"services": ["agent"]}
    assert payload["granularity"] == "weekly"
    assert payload["date_range_type"] == "last_7_days"
    assert payload["custom_date_start"] is None
    assert payload["custom_date_end"] is None
    assert payload["time_selection"] == {
        "mode": "preset",
        "preset": "last_7_days",
        "start_date": None,
        "end_date": None,
        "start_time": "00:00:00",
        "end_time": "23:59:59",
    }
    assert payload["name"].startswith("shopee-orders-services-v")


@pytest.mark.asyncio
async def test_create_config_allows_miaoshou_products_domain(collection_config_async_client):
    response = await collection_config_async_client.post(
        "/api/collection/configs",
        json={
            "name": "miaoshou-products-v1",
            "platform": "miaoshou",
            "account_ids": [],
            "data_domains": ["products"],
            "granularity": "daily",
            "time_selection": {
                "mode": "preset",
                "preset": "yesterday",
            },
            "schedule_enabled": False,
            "retry_count": 3,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["platform"] == "miaoshou"
    assert payload["data_domains"] == ["products"]


@pytest.mark.asyncio
async def test_update_config_normalizes_custom_time_selection_and_sub_domains(
    collection_config_async_client,
    collection_config_sqlite_session,
):
    config = CollectionConfig(
        name="shopee-services-v1",
        platform="shopee",
        account_ids=[],
        data_domains=["services"],
        sub_domains=None,
        granularity="daily",
        date_range_type="yesterday",
        custom_date_start=None,
        custom_date_end=None,
        schedule_enabled=False,
        schedule_cron=None,
        retry_count=3,
        is_active=True,
    )
    collection_config_sqlite_session.add(config)
    await collection_config_sqlite_session.commit()
    await collection_config_sqlite_session.refresh(config)

    response = await collection_config_async_client.put(
        f"/api/collection/configs/{config.id}",
        json={
            "data_domains": ["services"],
            "sub_domains": {
                "services": ["agent", "invalid"],
            },
            "granularity": "monthly",
            "time_selection": {
                "mode": "custom",
                "start_date": "2026-03-01",
                "end_date": "2026-03-31",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["data_domains"] == ["services"]
    assert payload["sub_domains"] == {"services": ["agent"]}
    assert payload["granularity"] == "monthly"
    assert payload["date_range_type"] == "custom"
    assert payload["custom_date_start"] == "2026-03-01"
    assert payload["custom_date_end"] == "2026-03-31"
    assert payload["time_selection"] == {
        "mode": "custom",
        "preset": None,
        "start_date": "2026-03-01",
        "end_date": "2026-03-31",
        "start_time": "00:00:00",
        "end_time": "23:59:59",
    }
