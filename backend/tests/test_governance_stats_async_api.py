from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from modules.core.db import CatalogFile


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest_asyncio.fixture
async def governance_client(monkeypatch):
    from backend.main import app
    from backend.models.database import get_async_db
    from backend.services import template_matcher as template_matcher_module

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS core"))
        await conn.run_sync(CatalogFile.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_async_db():
        async with session_factory() as session:
            yield session

    class FakeTemplateMatcher:
        async def get_template_coverage(self, platform=None):
            return {
                "total_combinations": 2,
                "covered_combinations": 1,
                "coverage_percentage": 50.0,
                "missing_combinations": [
                    {"domain": "orders", "granularity": "weekly"},
                ],
            }

    monkeypatch.setattr(
        template_matcher_module,
        "get_template_matcher",
        lambda db: FakeTemplateMatcher(),
        raising=False,
    )

    app.dependency_overrides[get_async_db] = override_get_async_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client, session_factory

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_governance_overview_uses_async_session(governance_client):
    client, session_factory = governance_client

    async with session_factory() as session:
        session.add_all(
            [
                CatalogFile(
                    file_path="data/raw/shopee/orders/orders_weekly_pending.xlsx",
                    file_name="orders_weekly_pending.xlsx",
                    source="data/raw",
                    platform_code="shopee",
                    source_platform="shopee",
                    data_domain="orders",
                    granularity="weekly",
                    status="pending",
                    first_seen_at=datetime.now(timezone.utc),
                ),
                CatalogFile(
                    file_path="data/raw/shopee/orders/orders_daily_ingested.xlsx",
                    file_name="orders_daily_ingested.xlsx",
                    source="data/raw",
                    platform_code="shopee",
                    source_platform="shopee",
                    data_domain="orders",
                    granularity="daily",
                    status="ingested",
                    first_seen_at=datetime.now(timezone.utc),
                    last_processed_at=datetime.now(timezone.utc),
                ),
            ]
        )
        await session.commit()

    response = await client.get("/api/field-mapping/governance/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["pending_files"] == 1
    assert payload["data"]["template_coverage"] == 50.0
    assert payload["data"]["today_auto_ingested"] == 1
    assert payload["data"]["missing_templates_count"] == 1


@pytest.mark.asyncio
async def test_governance_missing_templates_counts_pending_files(governance_client):
    client, session_factory = governance_client

    async with session_factory() as session:
        session.add_all(
            [
                CatalogFile(
                    file_path="data/raw/shopee/orders/orders_weekly_a.xlsx",
                    file_name="orders_weekly_a.xlsx",
                    source="data/raw",
                    platform_code="shopee",
                    source_platform="shopee",
                    data_domain="orders",
                    granularity="weekly",
                    status="pending",
                    first_seen_at=datetime.now(timezone.utc),
                ),
                CatalogFile(
                    file_path="data/raw/shopee/orders/orders_weekly_b.xlsx",
                    file_name="orders_weekly_b.xlsx",
                    source="data/raw",
                    platform_code="shopee",
                    source_platform="shopee",
                    data_domain="orders",
                    granularity="weekly",
                    status="pending",
                    first_seen_at=datetime.now(timezone.utc),
                ),
            ]
        )
        await session.commit()

    response = await client.get("/api/field-mapping/governance/missing-templates")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"] == [
        {
            "domain": "orders",
            "granularity": "weekly",
            "file_count": 2,
        }
    ]
