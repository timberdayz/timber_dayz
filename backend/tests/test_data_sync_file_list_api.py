from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from modules.core.db import CatalogFile, FieldMappingTemplate


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest_asyncio.fixture
async def file_list_client():
    from backend.main import app
    from backend.models.database import get_async_db

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS core"))
        await conn.run_sync(CatalogFile.__table__.create)
        await conn.run_sync(FieldMappingTemplate.__table__.create)

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
async def test_list_files_does_not_mark_services_file_as_template_covered_when_only_other_sub_domain_template_exists(
    file_list_client,
):
    client, session_factory = file_list_client

    async with session_factory() as session:
        session.add(
            FieldMappingTemplate(
                platform="tiktok",
                data_domain="services",
                granularity="daily",
                sub_domain="agent",
                template_name="tiktok_services_agent_daily_v1",
                version=1,
                status="published",
                header_row=2,
                header_columns=["日期", "客服"],
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        session.add(
            CatalogFile(
                file_path="data/raw/2026/tiktok_services_ai_assistant_daily_20260413_185520.xlsx",
                file_name="tiktok_services_ai_assistant_daily_20260413_185520.xlsx",
                source="data/raw",
                platform_code="tiktok",
                source_platform="tiktok",
                data_domain="services",
                granularity="daily",
                sub_domain="ai_assistant",
                status="pending",
                first_seen_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    response = await client.get(
        "/api/data-sync/files",
        params={"platform": "tiktok", "domain": "services", "granularity": "daily"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["total"] == 1
    file_row = payload["data"]["files"][0]
    assert file_row["sub_domain"] == "ai_assistant"
    assert file_row["has_template"] is False
    assert file_row["template_name"] is None
