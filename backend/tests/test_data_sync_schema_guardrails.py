from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from modules.core.db import CatalogFile, StagingInventory, StagingOrders, StagingProductMetrics


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest_asyncio.fixture
async def drifted_delete_client():
    from backend.main import app
    from backend.models.database import get_async_db

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(CatalogFile.__table__.create)
        await conn.run_sync(StagingOrders.__table__.create)
        await conn.run_sync(StagingProductMetrics.__table__.create)
        await conn.run_sync(StagingInventory.__table__.create)
        await conn.execute(
            text(
                """
                CREATE TABLE core.data_quarantine (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_file VARCHAR(500) NOT NULL,
                    row_number INTEGER,
                    row_data TEXT NOT NULL,
                    error_type VARCHAR(100) NOT NULL,
                    error_msg TEXT,
                    platform_code VARCHAR(32),
                    shop_id VARCHAR(64),
                    data_domain VARCHAR(64),
                    is_resolved BOOLEAN,
                    resolved_at DATETIME,
                    resolution_note TEXT,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )

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
async def test_delete_impact_returns_migration_hint_when_quarantine_column_missing(
    drifted_delete_client,
):
    client, session_factory = drifted_delete_client
    async with session_factory() as session:
        catalog = CatalogFile(
            file_path="data/raw/2026/drifted-orders.xlsx",
            file_name="drifted-orders.xlsx",
            source="data/raw",
            platform_code="tiktok",
            source_platform="miaoshou",
            data_domain="orders",
            granularity="weekly",
            status="ingested",
            first_seen_at=datetime.now(timezone.utc),
        )
        session.add(catalog)
        await session.commit()
        file_id = catalog.id

    response = await client.get(f"/api/data-sync/files/{file_id}/delete-impact")

    assert response.status_code == 500
    payload = response.json()
    assert payload["success"] is False
    assert "数据库结构未完成迁移" in payload["message"]
    assert "catalog_file_id" in payload["error"]["detail"]
    assert "alembic upgrade heads" in payload["error"]["detail"]


@pytest.mark.asyncio
async def test_delete_file_returns_migration_hint_when_quarantine_column_missing(
    drifted_delete_client,
):
    client, session_factory = drifted_delete_client
    async with session_factory() as session:
        catalog = CatalogFile(
            file_path="data/raw/2026/drifted-delete.xlsx",
            file_name="drifted-delete.xlsx",
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

    response = await client.delete(f"/api/data-sync/files/{file_id}")

    assert response.status_code == 500
    payload = response.json()
    assert payload["success"] is False
    assert "数据库结构未完成迁移" in payload["message"]
    assert "catalog_file_id" in payload["error"]["detail"]
    assert "alembic upgrade heads" in payload["error"]["detail"]
