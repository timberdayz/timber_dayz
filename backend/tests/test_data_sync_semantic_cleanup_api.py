from datetime import datetime, timezone
from pathlib import Path
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
async def semantic_cleanup_client():
    from backend.main import app
    from backend.models.database import get_async_db
    from backend.dependencies.auth import get_current_user

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS core"))
        await conn.run_sync(CatalogFile.__table__.create)

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
async def test_cleanup_semantic_anomalies_removes_pending_catalog_and_files(semantic_cleanup_client, tmp_path):
    client, session_factory, _app, _get_current_user = semantic_cleanup_client

    bad_file = tmp_path / "tiktok_products_tiktok_monthly_20260407_123005.xlsx"
    bad_meta = tmp_path / "tiktok_products_tiktok_monthly_20260407_123005.meta.json"
    bad_file.write_text("demo", encoding="utf-8")
    bad_meta.write_text("{}", encoding="utf-8")

    good_file = tmp_path / "tiktok_products_monthly_20260517_221824.xlsx"
    good_meta = tmp_path / "tiktok_products_monthly_20260517_221824.meta.json"
    good_file.write_text("demo", encoding="utf-8")
    good_meta.write_text("{}", encoding="utf-8")

    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        session.add_all(
            [
                CatalogFile(
                    file_path=str(bad_file),
                    file_name=bad_file.name,
                    source="data/raw",
                    platform_code="tiktok",
                    source_platform="tiktok",
                    data_domain="products",
                    granularity="monthly",
                    sub_domain="tiktok",
                    status="pending",
                    meta_file_path=str(bad_meta),
                    first_seen_at=now,
                ),
                CatalogFile(
                    file_path=str(good_file),
                    file_name=good_file.name,
                    source="data/raw",
                    platform_code="tiktok",
                    source_platform="tiktok",
                    data_domain="products",
                    granularity="monthly",
                    status="pending",
                    meta_file_path=str(good_meta),
                    first_seen_at=now,
                ),
            ]
        )
        await session.commit()

    response = await client.post("/api/data-sync/cleanup-semantic-anomalies")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["matched_count"] == 1
    assert payload["data"]["deleted_catalog_count"] == 1
    assert payload["data"]["deleted_file_count"] == 1
    assert payload["data"]["deleted_meta_count"] == 1
    assert payload["data"]["failures"] == []

    assert not bad_file.exists()
    assert not bad_meta.exists()
    assert good_file.exists()
    assert good_meta.exists()

    async with session_factory() as session:
        rows = (await session.execute(select(CatalogFile).order_by(CatalogFile.file_name.asc()))).scalars().all()

    assert [row.file_name for row in rows] == [good_file.name]


@pytest.mark.asyncio
async def test_cleanup_semantic_anomalies_keeps_catalog_delete_when_files_missing(semantic_cleanup_client, tmp_path):
    client, session_factory, _app, _get_current_user = semantic_cleanup_client

    missing_file = tmp_path / "shopee_services_shopee_monthly_20260407_122259.xlsx"
    missing_meta = tmp_path / "shopee_services_shopee_monthly_20260407_122259.meta.json"

    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        session.add(
            CatalogFile(
                file_path=str(missing_file),
                file_name=missing_file.name,
                source="data/raw",
                platform_code="shopee",
                source_platform="shopee",
                data_domain="services",
                granularity="monthly",
                sub_domain="shopee",
                status="pending",
                meta_file_path=str(missing_meta),
                first_seen_at=now,
            )
        )
        await session.commit()

    response = await client.post("/api/data-sync/cleanup-semantic-anomalies")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["matched_count"] == 1
    assert payload["data"]["deleted_catalog_count"] == 1
    assert payload["data"]["deleted_file_count"] == 0
    assert payload["data"]["deleted_meta_count"] == 0

    async with session_factory() as session:
        rows = (await session.execute(select(CatalogFile))).scalars().all()

    assert rows == []


@pytest.mark.asyncio
async def test_cleanup_semantic_anomalies_requires_admin_user(semantic_cleanup_client):
    client, session_factory, app, get_current_user = semantic_cleanup_client

    async def override_non_admin_user():
        return SimpleNamespace(user_id=2, username="viewer", is_active=True, status="active", is_superuser=False, roles=[])

    app.dependency_overrides[get_current_user] = override_non_admin_user

    response = await client.post("/api/data-sync/cleanup-semantic-anomalies")

    assert response.status_code == 403
