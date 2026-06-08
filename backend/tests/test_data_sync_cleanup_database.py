from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from modules.core.db import CatalogFile


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest_asyncio.fixture
async def cleanup_sqlite_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(CatalogFile.__table__.create)
        await conn.execute(
            text(
                """
                CREATE TABLE b_class.fact_tiktok_orders_weekly (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER,
                    order_id VARCHAR(128)
                )
                """
            )
        )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def cleanup_client():
    from backend.dependencies.auth import get_current_user
    from backend.main import app
    from backend.models.database import get_async_db

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(CatalogFile.__table__.create)
        await conn.execute(
            text(
                """
                CREATE TABLE b_class.fact_tiktok_orders_weekly (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER,
                    order_id VARCHAR(128)
                )
                """
            )
        )

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
        yield client, session_factory

    app.dependency_overrides.clear()
    await engine.dispose()


async def _add_catalog_file(session, tmp_path, name: str, status: str, *, file_exists=True, meta_exists=True):
    file_path = tmp_path / f"{name}.xlsx"
    meta_path = tmp_path / f"{name}.meta.json"
    if file_exists:
        file_path.write_text("raw", encoding="utf-8")
    if meta_exists:
        meta_path.write_text("{}", encoding="utf-8")

    catalog = CatalogFile(
        file_path=str(file_path),
        file_name=file_path.name,
        source="data/raw",
        platform_code="tiktok",
        source_platform="miaoshou",
        data_domain="orders",
        granularity="weekly",
        status=status,
        meta_file_path=str(meta_path),
        first_seen_at=datetime.now(timezone.utc),
    )
    session.add(catalog)
    await session.flush()
    await session.execute(
        text(
            """
            INSERT INTO b_class.fact_tiktok_orders_weekly (file_id, order_id)
            VALUES (:file_id, :order_id)
            """
        ),
        {"file_id": catalog.id, "order_id": f"order-{name}"},
    )
    return catalog


async def _seed_cleanup_records(session, tmp_path):
    records = {
        "ingested_rebuildable": await _add_catalog_file(
            session, tmp_path, "ingested-rebuildable", "ingested"
        ),
        "partial_rebuildable": await _add_catalog_file(
            session, tmp_path, "partial-rebuildable", "partial_success"
        ),
        "missing_file": await _add_catalog_file(
            session, tmp_path, "missing-file", "ingested", file_exists=False
        ),
        "missing_meta": await _add_catalog_file(
            session, tmp_path, "missing-meta", "partial_success", meta_exists=False
        ),
        "failed": await _add_catalog_file(
            session, tmp_path, "failed-missing-file", "failed", file_exists=False
        ),
        "processing": await _add_catalog_file(
            session, tmp_path, "processing-rebuildable", "processing"
        ),
    }
    await session.commit()
    return records


@pytest.mark.asyncio
async def test_cleanup_database_impact_counts_without_mutating_catalog_statuses(
    cleanup_sqlite_session,
    tmp_path,
):
    from backend.services.data_sync_cleanup_service import DataSyncCleanupService

    records = await _seed_cleanup_records(cleanup_sqlite_session, tmp_path)
    service = DataSyncCleanupService(cleanup_sqlite_session)

    impact = await service.analyze_cleanup_impact()

    assert impact["total_fact_rows"] == 6
    assert impact["fact_table_counts"] == {"fact_tiktok_orders_weekly": 6}
    assert impact["resettable_files_count"] == 2
    assert impact["source_missing_files_count"] == 2
    assert impact["file_missing_files_count"] == 1
    assert impact["meta_missing_files_count"] == 1
    assert impact["skipped_failed_count"] == 1
    assert impact["skipped_processing_count"] == 1

    for key, catalog in records.items():
        refreshed = await cleanup_sqlite_session.get(CatalogFile, catalog.id)
        assert refreshed.status == catalog.status, key


@pytest.mark.asyncio
async def test_cleanup_database_deletes_facts_and_only_resets_rebuildable_files(
    cleanup_sqlite_session,
    tmp_path,
):
    from backend.services.data_sync_cleanup_service import DataSyncCleanupService

    records = await _seed_cleanup_records(cleanup_sqlite_session, tmp_path)
    service = DataSyncCleanupService(cleanup_sqlite_session)

    result = await service.cleanup_database()

    assert result["total_deleted_rows"] == 6
    assert result["deleted_counts"] == {"fact_tiktok_orders_weekly": 6}
    assert result["reset_files_count"] == 2
    assert result["marked_source_missing_count"] == 2
    assert result["skipped_failed_count"] == 1
    assert result["skipped_processing_count"] == 1

    expected_statuses = {
        "ingested_rebuildable": "pending",
        "partial_rebuildable": "pending",
        "missing_file": "source_missing",
        "missing_meta": "source_missing",
        "failed": "failed",
        "processing": "processing",
    }
    for key, expected_status in expected_statuses.items():
        refreshed = await cleanup_sqlite_session.get(CatalogFile, records[key].id)
        assert refreshed.status == expected_status, key

    missing_file = await cleanup_sqlite_session.get(CatalogFile, records["missing_file"].id)
    assert "原始文件缺失" in missing_file.error_message
    missing_meta = await cleanup_sqlite_session.get(CatalogFile, records["missing_meta"].id)
    assert "伴生文件缺失" in missing_meta.error_message

    remaining_fact = await cleanup_sqlite_session.execute(
        text("SELECT COUNT(*) FROM b_class.fact_tiktok_orders_weekly")
    )
    assert remaining_fact.scalar() == 0

    pending_rows = await cleanup_sqlite_session.execute(
        select(CatalogFile).where(CatalogFile.status == "pending")
    )
    assert len(pending_rows.scalars().all()) == 2


@pytest.mark.asyncio
async def test_cleanup_database_impact_endpoint_returns_preview_counts(
    cleanup_client,
    tmp_path,
):
    client, session_factory = cleanup_client
    async with session_factory() as session:
        await _seed_cleanup_records(session, tmp_path)

    response = await client.get("/api/data-sync/cleanup-database/impact")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["total_fact_rows"] == 6
    assert payload["data"]["resettable_files_count"] == 2
    assert payload["data"]["source_missing_files_count"] == 2


@pytest.mark.asyncio
async def test_governance_stats_counts_source_missing_separately(
    cleanup_client,
    tmp_path,
):
    client, session_factory = cleanup_client
    missing_file = tmp_path / "source-missing.xlsx"
    async with session_factory() as session:
        session.add(
            CatalogFile(
                file_path=str(missing_file),
                file_name=missing_file.name,
                source="data/raw",
                platform_code="tiktok",
                source_platform="miaoshou",
                data_domain="orders",
                granularity="weekly",
                status="source_missing",
                error_message="清空事实数据时跳过：原始文件缺失，无法自动重建",
                first_seen_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    response = await client.get("/api/data-sync/governance/stats")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["source_missing_count"] == 1
    assert payload["data"]["pending_count"] == 0
    assert payload["data"]["ingested_count"] == 0
