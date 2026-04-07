from datetime import datetime, timezone

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
async def file_delete_client():
    from backend.main import app
    from backend.models.database import get_async_db

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

    app.dependency_overrides[get_async_db] = override_get_async_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client, session_factory

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_delete_impact_returns_platform_and_fact_counts(
    file_delete_client,
):
    pg_async_client, session_factory = file_delete_client
    async with session_factory() as session:
        catalog = CatalogFile(
            file_path="data/raw/2026/tiktok_orders_weekly_20260331_140511.xlsx",
            file_name="tiktok_orders_weekly_20260331_140511.xlsx",
            source="data/raw",
            platform_code="tiktok",
            source_platform="miaoshou",
            data_domain="orders",
            granularity="weekly",
            status="ingested",
            first_seen_at=datetime.now(timezone.utc),
        )
        session.add(catalog)
        await session.flush()

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
            {"file_id": catalog.id},
        )
        await session.commit()
        file_id = catalog.id

    response = await pg_async_client.get(f"/api/data-sync/files/{file_id}/delete-impact")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["file_id"] == file_id
    assert payload["data"]["platform_code"] == "tiktok"
    assert payload["data"]["fact_rows"] == 2


@pytest.mark.asyncio
async def test_delete_file_endpoint_removes_file_record(
    file_delete_client,
    tmp_path,
):
    file_path = tmp_path / "delete-me.xlsx"
    meta_path = tmp_path / "delete-me.meta.json"
    file_path.write_text("demo", encoding="utf-8")
    meta_path.write_text("{}", encoding="utf-8")

    pg_async_client, session_factory = file_delete_client
    async with session_factory() as session:
        catalog = CatalogFile(
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
        session.add(catalog)
        await session.commit()
        file_id = catalog.id

    response = await pg_async_client.delete(f"/api/data-sync/files/{file_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["file_id"] == file_id
    assert payload["data"]["deleted_catalog"] is True
