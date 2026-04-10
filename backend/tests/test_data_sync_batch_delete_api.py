from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from modules.core.db import CatalogFile, DataQuarantine, StagingInventory, StagingOrders, StagingProductMetrics


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest_asyncio.fixture
async def batch_delete_client():
    from backend.main import app
    from backend.models.database import get_async_db
    from backend.dependencies.auth import get_current_user

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(CatalogFile.__table__.create)
        await conn.run_sync(DataQuarantine.__table__.create)
        await conn.run_sync(StagingOrders.__table__.create)
        await conn.run_sync(StagingProductMetrics.__table__.create)
        await conn.run_sync(StagingInventory.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_async_db():
        async with session_factory() as session:
            yield session

    async def override_current_user():
        return SimpleNamespace(user_id=1, username="admin", is_active=True, status="active", is_superuser=True, roles=[])

    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_current_user] = override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client, session_factory, app, get_current_user

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_batch_delete_impact_returns_aggregate_counts(batch_delete_client):
    client, session_factory, _app, _get_current_user = batch_delete_client

    async with session_factory() as session:
        pending_catalog = CatalogFile(
            file_path="data/raw/2026/batch-delete-a.xlsx",
            file_name="batch-delete-a.xlsx",
            source="data/raw",
            platform_code="tiktok",
            source_platform="miaoshou",
            data_domain="orders",
            granularity="weekly",
            status="pending",
            first_seen_at=datetime.now(timezone.utc),
        )
        processing_catalog = CatalogFile(
            file_path="data/raw/2026/batch-delete-b.xlsx",
            file_name="batch-delete-b.xlsx",
            source="data/raw",
            platform_code="tiktok",
            source_platform="miaoshou",
            data_domain="orders",
            granularity="weekly",
            status="processing",
            first_seen_at=datetime.now(timezone.utc),
        )
        session.add_all([pending_catalog, processing_catalog])
        await session.flush()

        session.add(
            DataQuarantine(
                source_file=pending_catalog.file_name,
                catalog_file_id=pending_catalog.id,
                row_data="{}",
                error_type="validation_error",
                error_msg="bad row",
                platform_code="tiktok",
                data_domain="orders",
            )
        )
        session.add(
            StagingOrders(
                platform_code="tiktok",
                shop_id="shop-1",
                order_id="order-1",
                order_data={"id": "order-1"},
                file_id=pending_catalog.id,
            )
        )
        await session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS b_class.fact_tiktok_orders_weekly (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER,
                    order_id VARCHAR(128)
                )
                """
            )
        )
        await session.execute(
            text(
                """
                INSERT INTO b_class.fact_tiktok_orders_weekly (file_id, order_id)
                VALUES (:file_id, 'order-a'), (:file_id, 'order-b')
                """
            ),
            {"file_id": pending_catalog.id},
        )
        await session.commit()

    response = await client.post(
        "/api/data-sync/files/batch-delete-impact",
        json={"file_ids": [pending_catalog.id, processing_catalog.id, 999999]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["requested_count"] == 3
    assert payload["data"]["found_count"] == 2
    assert payload["data"]["missing_count"] == 1
    assert payload["data"]["deletable_count"] == 1
    assert payload["data"]["processing_count"] == 1
    assert payload["data"]["quarantine_rows"] == 1
    assert payload["data"]["staging_rows"] == 1
    assert payload["data"]["fact_rows"] == 2


@pytest.mark.asyncio
async def test_batch_delete_deletes_pending_and_skips_processing(batch_delete_client, tmp_path):
    client, session_factory, _app, _get_current_user = batch_delete_client

    file_path = tmp_path / "batch-delete.xlsx"
    meta_path = tmp_path / "batch-delete.meta.json"
    file_path.write_text("demo", encoding="utf-8")
    meta_path.write_text("{}", encoding="utf-8")

    async with session_factory() as session:
        pending_catalog = CatalogFile(
            file_path=str(file_path),
            file_name=file_path.name,
            source="data/raw",
            platform_code="tiktok",
            source_platform="miaoshou",
            data_domain="orders",
            granularity="weekly",
            status="pending",
            meta_file_path=str(meta_path),
            first_seen_at=datetime.now(timezone.utc),
        )
        processing_catalog = CatalogFile(
            file_path="data/raw/2026/processing.xlsx",
            file_name="processing.xlsx",
            source="data/raw",
            platform_code="tiktok",
            source_platform="miaoshou",
            data_domain="orders",
            granularity="weekly",
            status="processing",
            first_seen_at=datetime.now(timezone.utc),
        )
        session.add_all([pending_catalog, processing_catalog])
        await session.commit()
        pending_id = pending_catalog.id
        processing_id = processing_catalog.id

    response = await client.request(
        "DELETE",
        "/api/data-sync/files/batch",
        json={"file_ids": [pending_id, processing_id]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["requested_count"] == 2
    assert payload["data"]["deleted_count"] == 1
    assert payload["data"]["skipped_count"] == 1

    item_by_id = {item["file_id"]: item for item in payload["data"]["items"]}
    assert item_by_id[pending_id]["outcome"] == "deleted"
    assert item_by_id[processing_id]["outcome"] == "skipped"

    async with session_factory() as session:
        deleted_catalog = await session.get(CatalogFile, pending_id)
        kept_catalog = await session.get(CatalogFile, processing_id)
        assert deleted_catalog is None
        assert kept_catalog is not None

    assert not file_path.exists()
    assert not meta_path.exists()


@pytest.mark.asyncio
async def test_batch_delete_endpoints_require_authenticated_user(batch_delete_client):
    client, session_factory, app, get_current_user = batch_delete_client
    async with session_factory() as session:
        catalog = CatalogFile(
            file_path="data/raw/2026/auth-batch.xlsx",
            file_name="auth-batch.xlsx",
            source="data/raw",
            platform_code="tiktok",
            source_platform="miaoshou",
            data_domain="orders",
            granularity="weekly",
            status="pending",
            first_seen_at=datetime.now(timezone.utc),
        )
        session.add(catalog)
        await session.commit()
        file_id = catalog.id

    app.dependency_overrides.pop(get_current_user, None)

    impact_response = await client.post(
        "/api/data-sync/files/batch-delete-impact",
        json={"file_ids": [file_id]},
    )
    delete_response = await client.request(
        "DELETE",
        "/api/data-sync/files/batch",
        json={"file_ids": [file_id]},
    )

    assert impact_response.status_code == 401
    assert delete_response.status_code == 401


@pytest.mark.asyncio
async def test_batch_delete_endpoints_require_admin_user(batch_delete_client):
    client, session_factory, app, get_current_user = batch_delete_client
    async with session_factory() as session:
        catalog = CatalogFile(
            file_path="data/raw/2026/non-admin-batch.xlsx",
            file_name="non-admin-batch.xlsx",
            source="data/raw",
            platform_code="tiktok",
            source_platform="miaoshou",
            data_domain="orders",
            granularity="weekly",
            status="pending",
            first_seen_at=datetime.now(timezone.utc),
        )
        session.add(catalog)
        await session.commit()
        file_id = catalog.id

    async def override_non_admin_user():
        return SimpleNamespace(user_id=2, username="viewer", is_active=True, status="active", is_superuser=False, roles=[])

    app.dependency_overrides[get_current_user] = override_non_admin_user

    impact_response = await client.post(
        "/api/data-sync/files/batch-delete-impact",
        json={"file_ids": [file_id]},
    )
    delete_response = await client.request(
        "DELETE",
        "/api/data-sync/files/batch",
        json={"file_ids": [file_id]},
    )

    assert impact_response.status_code == 403
    assert delete_response.status_code == 403
