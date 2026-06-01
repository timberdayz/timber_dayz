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
async def governance_client(monkeypatch):
    from backend.main import app
    from backend.dependencies.auth import get_current_user
    from backend.models.database import get_async_db
    from backend.services import template_matcher as template_matcher_module

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS core"))
        await conn.run_sync(CatalogFile.__table__.create)
        await conn.run_sync(FieldMappingTemplate.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_async_db():
        async with session_factory() as session:
            yield session

    async def override_current_user():
        return type(
            "_AdminUser",
            (),
            {
                "user_id": 1,
                "username": "admin",
                "is_active": True,
                "status": "active",
                "is_superuser": True,
                "roles": [],
            },
        )()

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
    app.dependency_overrides[get_current_user] = override_current_user

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


@pytest.mark.asyncio
async def test_data_sync_governance_stats_reports_ready_update_required_and_missing_counts(governance_client, monkeypatch):
    client, session_factory = governance_client

    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        session.add(
            FieldMappingTemplate(
                platform="tiktok",
                data_domain="products",
                granularity="monthly",
                sub_domain=None,
                template_name="tiktok_products__monthly_v2",
                version=2,
                status="published",
                header_row=2,
                header_columns=["日期", "商品交易总额", "退款金额"],
                created_at=now,
                updated_at=now,
            )
        )
        session.add_all(
            [
                CatalogFile(
                    file_path="data/raw/2026/products-ready.xlsx",
                    file_name="products-ready.xlsx",
                    source="data/raw",
                    platform_code="tiktok",
                    source_platform="tiktok",
                    data_domain="products",
                    granularity="monthly",
                    status="pending",
                    first_seen_at=now,
                ),
                CatalogFile(
                    file_path="data/raw/2026/products-update.xlsx",
                    file_name="products-update.xlsx",
                    source="data/raw",
                    platform_code="tiktok",
                    source_platform="tiktok",
                    data_domain="products",
                    granularity="monthly",
                    status="pending",
                    first_seen_at=now,
                ),
                CatalogFile(
                    file_path="data/raw/2026/services-missing.xlsx",
                    file_name="services-missing.xlsx",
                    source="data/raw",
                    platform_code="tiktok",
                    source_platform="tiktok",
                    data_domain="services",
                    granularity="daily",
                    sub_domain="ai_assistant",
                    status="pending",
                    first_seen_at=now,
                ),
            ]
        )
        await session.commit()

    async def _fake_readiness(self, file_id, use_template_header_row=True):
        mapping = {
            1: {"ready": True, "template_status": "ready", "should_auto_sync": True},
            2: {"ready": False, "template_status": "update_required", "should_auto_sync": False},
            3: {"ready": False, "template_status": "missing", "should_auto_sync": False},
        }
        row = mapping.get(file_id, {"ready": False, "template_status": "missing", "should_auto_sync": False})
        return {
            "file_id": file_id,
            "file_name": f"file-{file_id}.xlsx",
            "template_update_required": row["template_status"] == "update_required",
            "update_reason": None,
            **row,
        }

    monkeypatch.setattr(
        "backend.services.data_sync_service.DataSyncService.get_file_sync_readiness",
        _fake_readiness,
    )

    response = await client.get("/api/data-sync/governance/stats")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["pending_count"] == 3
    assert payload["data"]["ready_to_sync_count"] == 1
    assert payload["data"]["template_update_required_count"] == 1
    assert payload["data"]["missing_template_count"] == 1


@pytest.mark.asyncio
async def test_data_sync_governance_stats_excludes_semantic_anomaly_pending_files(governance_client, monkeypatch):
    client, session_factory = governance_client

    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        session.add_all(
            [
                CatalogFile(
                    file_path="data/raw/2026/tiktok_products_monthly_20260517_221824.xlsx",
                    file_name="tiktok_products_monthly_20260517_221824.xlsx",
                    source="data/raw",
                    platform_code="tiktok",
                    source_platform="tiktok",
                    data_domain="products",
                    granularity="monthly",
                    status="pending",
                    first_seen_at=now,
                ),
                CatalogFile(
                    file_path="data/raw/2026/tiktok_products_tiktok_monthly_20260407_123005.xlsx",
                    file_name="tiktok_products_tiktok_monthly_20260407_123005.xlsx",
                    source="data/raw",
                    platform_code="tiktok",
                    source_platform="tiktok",
                    data_domain="products",
                    granularity="monthly",
                    sub_domain="tiktok",
                    status="pending",
                    first_seen_at=now,
                ),
            ]
        )
        await session.commit()

    async def _fake_readiness(self, file_id, use_template_header_row=True):
        return {
            "file_id": file_id,
            "file_name": f"file-{file_id}.xlsx",
            "template_update_required": False,
            "update_reason": None,
            "ready": True,
            "template_status": "ready",
            "should_auto_sync": True,
        }

    monkeypatch.setattr(
        "backend.services.data_sync_service.DataSyncService.get_file_sync_readiness",
        _fake_readiness,
    )

    response = await client.get("/api/data-sync/governance/stats")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["pending_count"] == 1
    assert payload["data"]["ready_to_sync_count"] == 1
