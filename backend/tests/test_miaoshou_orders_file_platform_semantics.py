from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from httpx import ASGITransport, AsyncClient

from modules.core.db import CatalogFile
from modules.core.file_naming import StandardFileName
from modules.services.catalog_scanner import register_single_file
from modules.services.metadata_manager import MetadataManager


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


def test_register_single_file_uses_business_platform_and_preserves_miaoshou_source(
    tmp_path,
    monkeypatch,
):
    import backend.services.platform_table_manager as platform_table_manager_module
    from modules.services import catalog_scanner as catalog_scanner_module

    engine = create_engine(f"sqlite:///{tmp_path / 'catalog.db'}", future=True)
    CatalogFile.__table__.create(engine)
    monkeypatch.setattr(catalog_scanner_module, "_get_engine", lambda: engine)
    monkeypatch.setattr(
        platform_table_manager_module,
        "get_platform_table_manager",
        lambda _session: type(
            "_NoopTableManager",
            (),
            {"ensure_table_exists": staticmethod(lambda **_kwargs: "fact_tiktok_orders_weekly")},
        )(),
    )

    raw_dir = tmp_path / "data" / "raw" / "2026"
    raw_dir.mkdir(parents=True, exist_ok=True)

    file_path = raw_dir / StandardFileName.generate(
        source_platform="tiktok",
        data_domain="orders",
        granularity="weekly",
        timestamp="20260331_140511",
        ext="xls",
    )
    file_path.write_text("demo", encoding="utf-8")

    MetadataManager.create_meta_file(
        file_path,
        business_metadata={
            "source_platform": "tiktok",
            "data_domain": "orders",
            "sub_domain": "",
            "date_from": "2026-03-08",
            "date_to": "2026-03-14",
        },
        collection_info={
            "method": "python_component",
            "collection_platform": "miaoshou",
            "account": "acc",
            "shop_id": "shop",
            "original_path": r"temp\downloads\task-1\miaoshou\acc\shop\orders\tiktok\manual\export.xls",
            "collected_at": datetime.now().isoformat(),
        },
    )

    file_id = register_single_file(str(file_path))

    assert file_id is not None

    with Session(engine) as session:
        record = session.execute(
            select(CatalogFile).where(CatalogFile.id == file_id)
        ).scalar_one()

    assert record.platform_code == "tiktok"
    assert record.source_platform == "miaoshou"
    assert record.data_domain == "orders"
    assert record.sub_domain in (None, "")


@pytest.fixture
async def catalog_async_client(tmp_path):
    from backend.main import app
    from backend.models.database import get_async_db

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'catalog-async.db'}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(CatalogFile.__table__.create)

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
async def test_file_groups_prefers_platform_code_over_source_platform(
    catalog_async_client,
):
    async_client, session_factory = catalog_async_client

    async with session_factory() as session:
        session.add(
            CatalogFile(
                file_path="data/raw/2026/tiktok_orders_weekly_20260331_140511.xls",
                file_name="tiktok_orders_weekly_20260331_140511.xls",
                source="data/raw",
                platform_code="tiktok",
                source_platform="miaoshou",
                data_domain="orders",
                granularity="weekly",
                status="pending",
                first_seen_at=datetime.now(),
            )
        )
        await session.commit()

    response = await async_client.get("/api/field-mapping/file-groups")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["platforms"] == ["tiktok"]
    assert "tiktok" in payload["data"]["files"]
    assert "miaoshou" not in payload["data"]["files"]
