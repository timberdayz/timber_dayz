from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from modules.core.db import CatalogFile, DataQuarantine, StagingInventory, StagingOrders, StagingProductMetrics


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest_asyncio.fixture
async def delete_sqlite_session():
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
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_analyze_pending_file_delete_returns_local_and_catalog_impact(
    delete_sqlite_session,
    tmp_path,
):
    from backend.services.catalog_file_delete_service import CatalogFileDeleteService

    file_path = tmp_path / "pending-orders.xlsx"
    meta_path = tmp_path / "pending-orders.meta.json"
    file_path.write_text("pending", encoding="utf-8")
    meta_path.write_text("{}", encoding="utf-8")

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
    delete_sqlite_session.add(catalog)
    await delete_sqlite_session.flush()

    delete_sqlite_session.add(
        DataQuarantine(
            source_file=file_path.name,
            catalog_file_id=catalog.id,
            row_data="{}",
            error_type="validation_error",
            error_msg="bad row",
            platform_code="tiktok",
            data_domain="orders",
        )
    )
    await delete_sqlite_session.commit()

    service = CatalogFileDeleteService(delete_sqlite_session)

    impact = await service.analyze_delete_impact(catalog.id)

    assert impact.file_id == catalog.id
    assert impact.platform_code == "tiktok"
    assert impact.source_platform == "miaoshou"
    assert impact.status == "pending"
    assert impact.local_file_exists is True
    assert impact.meta_file_exists is True
    assert impact.quarantine_rows == 1
    assert impact.staging_rows == 0
    assert impact.fact_rows == 0
    assert impact.can_delete is True


@pytest.mark.asyncio
async def test_delete_ingested_file_removes_fact_and_catalog_rows(
    delete_sqlite_session,
    tmp_path,
):
    from backend.services.catalog_file_delete_service import CatalogFileDeleteService

    file_path = tmp_path / "ingested-orders.xlsx"
    meta_path = tmp_path / "ingested-orders.meta.json"
    file_path.write_text("ingested", encoding="utf-8")
    meta_path.write_text("{}", encoding="utf-8")

    catalog = CatalogFile(
        file_path=str(file_path),
        file_name=file_path.name,
        source="data/raw",
        platform_code="tiktok",
        source_platform="miaoshou",
        data_domain="orders",
        granularity="weekly",
        status="ingested",
        meta_file_path=str(meta_path),
        first_seen_at=datetime.now(timezone.utc),
    )
    delete_sqlite_session.add(catalog)
    await delete_sqlite_session.flush()

    delete_sqlite_session.add(
        StagingOrders(
            platform_code="tiktok",
            shop_id="shop-1",
            order_id="order-1",
            order_data={"id": "order-1"},
            file_id=catalog.id,
        )
    )
    delete_sqlite_session.add(
        DataQuarantine(
            source_file=file_path.name,
            catalog_file_id=catalog.id,
            row_data="{}",
            error_type="validation_error",
            error_msg="bad row",
            platform_code="tiktok",
            data_domain="orders",
        )
    )

    await delete_sqlite_session.execute(
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
    await delete_sqlite_session.execute(
        text(
            """
            INSERT INTO b_class.fact_tiktok_orders_weekly (file_id, order_id)
            VALUES (:file_id, 'order-a'), (:file_id, 'order-b'), (:file_id, 'order-c')
            """
        ),
        {"file_id": catalog.id},
    )
    await delete_sqlite_session.commit()

    service = CatalogFileDeleteService(delete_sqlite_session)

    result = await service.delete_catalog_file(catalog.id, force=True)

    assert result.file_id == catalog.id
    assert result.deleted_catalog is True
    assert result.deleted_staging_rows == 1
    assert result.deleted_quarantine_rows == 1
    assert result.deleted_fact_rows == 3
    assert result.fact_table_name == "fact_tiktok_orders_weekly"
    assert result.deleted_file is True
    assert result.deleted_meta is True

    remaining_catalog = await delete_sqlite_session.execute(
        select(CatalogFile).where(CatalogFile.id == catalog.id)
    )
    assert remaining_catalog.scalar_one_or_none() is None

    remaining_staging = await delete_sqlite_session.execute(
        select(StagingOrders).where(StagingOrders.file_id == catalog.id)
    )
    assert remaining_staging.scalars().all() == []

    remaining_fact = await delete_sqlite_session.execute(
        text("SELECT COUNT(*) FROM b_class.fact_tiktok_orders_weekly WHERE file_id = :file_id"),
        {"file_id": catalog.id},
    )
    assert remaining_fact.scalar() == 0
