from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
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
async def data_sync_client(tmp_path, monkeypatch):
    from backend.main import app
    from backend.dependencies.auth import get_current_user
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

    class _MockUser:
        id = 1
        username = "test_admin"
        is_active = True
        is_superuser = True
        role_id = 1

    async def override_current_user():
        return _MockUser()

    class _ExecutorManagerStub:
        async def run_cpu_intensive(self, _fn, *_args, **_kwargs):
            return pd.DataFrame(columns=["订单编号", "金额"])

    async def _fake_status(self, catalog_file, *, template=None, current_columns=None, sample_rows=None):
        if "alias" in catalog_file.file_name:
            return {
                "template_status": "alias_only",
                "has_template": True,
                "template_name": getattr(template, "template_name", "demo"),
                "template_header_row": getattr(template, "header_row", None),
                "template_update_required": False,
                "update_reason": None,
                "error_code": None,
                "should_auto_sync": True,
                "exact_match": False,
                "semantic_match": True,
                "header_changes": {
                    "detected": True,
                    "match_rate": 100.0,
                    "added_fields": ["TikTok 平台佣金"],
                    "removed_fields": ["TikTok Shop平台佣金"],
                },
            }
        if "drift" in catalog_file.file_name:
            return {
                "template_status": "update_required",
                "has_template": True,
                "template_name": getattr(template, "template_name", "demo"),
                "template_header_row": getattr(template, "header_row", None),
                "template_update_required": True,
                "update_reason": "新增1个字段,删除1个字段",
                "error_code": "HEADER_CHANGED",
                "should_auto_sync": False,
                "exact_match": False,
                "semantic_match": False,
                "header_changes": {
                    "detected": True,
                    "match_rate": 91.7,
                    "added_fields": ["新字段"],
                    "removed_fields": ["旧字段"],
                },
            }
        return {
            "template_status": "ready",
            "has_template": True,
            "template_name": getattr(template, "template_name", "demo"),
            "template_header_row": getattr(template, "header_row", None),
            "template_update_required": False,
            "update_reason": None,
            "error_code": None,
            "should_auto_sync": True,
            "exact_match": True,
            "semantic_match": True,
            "header_changes": {
                "detected": False,
                "match_rate": 100.0,
                "added_fields": [],
                "removed_fields": [],
            },
        }

    monkeypatch.setattr(
        "backend.services.data_sync_service.get_executor_manager",
        lambda: _ExecutorManagerStub(),
    )
    monkeypatch.setattr(
        "backend.services.excel_parser.ExcelParser.read_excel",
        staticmethod(lambda *_args, **_kwargs: pd.DataFrame(columns=["订单编号", "金额"])),
    )
    monkeypatch.setattr(
        "backend.services.data_sync_template_status_service.DataSyncTemplateStatusService.evaluate_catalog_file",
        _fake_status,
    )

    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_current_user] = override_current_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client, session_factory, tmp_path

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_file_list_and_governance_share_alias_only_and_update_required_status(data_sync_client):
    client, session_factory, tmp_path = data_sync_client
    now = datetime.now(timezone.utc)

    alias_path = tmp_path / "tiktok_orders_alias.xlsx"
    drift_path = tmp_path / "tiktok_orders_drift.xlsx"
    alias_path.write_text("demo", encoding="utf-8")
    drift_path.write_text("demo", encoding="utf-8")

    async with session_factory() as session:
        session.add(
            FieldMappingTemplate(
                platform="tiktok",
                data_domain="orders",
                granularity="monthly",
                sub_domain=None,
                template_name="tiktok_orders__monthly_v2",
                version=2,
                status="published",
                header_row=1,
                header_columns=["订单编号", "金额"],
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            FieldMappingTemplate(
                platform="tiktok",
                data_domain="orders",
                granularity="weekly",
                sub_domain=None,
                template_name="tiktok_orders__weekly_v1",
                version=1,
                status="published",
                header_row=1,
                header_columns=["订单编号", "金额"],
                created_at=now,
                updated_at=now,
            )
        )
        session.add_all(
            [
                CatalogFile(
                    file_path=str(alias_path),
                    file_name=alias_path.name,
                    source="data/raw",
                    platform_code="tiktok",
                    source_platform="tiktok",
                    data_domain="orders",
                    granularity="monthly",
                    status="pending",
                    first_seen_at=now,
                ),
                CatalogFile(
                    file_path=str(drift_path),
                    file_name=drift_path.name,
                    source="data/raw",
                    platform_code="tiktok",
                    source_platform="tiktok",
                    data_domain="orders",
                    granularity="weekly",
                    status="pending",
                    first_seen_at=now,
                ),
            ]
        )
        await session.commit()

    file_response = await client.get("/api/data-sync/files", params={"status": "pending"})
    assert file_response.status_code == 200
    file_payload = file_response.json()["data"]["files"]
    by_name = {row["file_name"]: row for row in file_payload}
    assert by_name["tiktok_orders_alias.xlsx"]["template_status"] == "alias_only"
    assert by_name["tiktok_orders_alias.xlsx"]["governance_status"] == "non_breaking_drift"
    assert by_name["tiktok_orders_alias.xlsx"]["template_update_required"] is False
    assert by_name["tiktok_orders_drift.xlsx"]["template_status"] == "update_required"
    assert by_name["tiktok_orders_drift.xlsx"]["governance_status"] == "breaking_drift"
    assert by_name["tiktok_orders_drift.xlsx"]["template_update_required"] is True

    coverage_response = await client.get("/api/data-sync/governance/detailed-coverage")
    assert coverage_response.status_code == 200
    coverage = coverage_response.json()["data"]

    assert coverage["summary"]["needs_update_count"] == 1
    assert coverage["summary"]["breaking_drift_count"] == 1
    assert coverage["summary"]["non_breaking_drift_count"] == 1
    assert len(coverage["current_needs_update"]) == 1
    assert coverage["current_needs_update"][0]["sample_file_name"] == "tiktok_orders_drift.xlsx"
    assert all(item["governance_status"] != "breaking_drift" for item in coverage["current_covered"])
    assert {item["sample_file_name"] for item in coverage["current_covered"]} == {"tiktok_orders_alias.xlsx"}


@pytest.mark.asyncio
async def test_governance_detailed_coverage_includes_failed_header_changed_files_as_update_samples(
    data_sync_client,
):
    client, session_factory, tmp_path = data_sync_client
    now = datetime.now(timezone.utc)

    failed_path = tmp_path / "tiktok_orders_drift_failed.xlsx"
    failed_path.write_text("demo", encoding="utf-8")

    async with session_factory() as session:
        session.add(
            FieldMappingTemplate(
                platform="tiktok",
                data_domain="orders",
                granularity="monthly",
                sub_domain=None,
                template_name="tiktok_orders__monthly_v2",
                version=2,
                status="published",
                header_row=1,
                header_columns=["订单编号", "金额"],
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            CatalogFile(
                file_path=str(failed_path),
                file_name=failed_path.name,
                source="data/raw",
                platform_code="tiktok",
                source_platform="tiktok",
                data_domain="orders",
                granularity="monthly",
                status="failed",
                first_seen_at=now,
            )
        )
        await session.commit()

    response = await client.get("/api/data-sync/governance/detailed-coverage")

    assert response.status_code == 200
    coverage = response.json()["data"]
    assert coverage["summary"]["needs_update_count"] == 1
    assert coverage["needs_update"][0]["sample_file_name"] == "tiktok_orders_drift_failed.xlsx"


@pytest.mark.asyncio
async def test_governance_detailed_coverage_skips_temp_development_sample_files(
    data_sync_client,
):
    client, session_factory, tmp_path = data_sync_client
    now = datetime.now(timezone.utc)

    real_sample_path = tmp_path / "shopee_products_daily_real.xlsx"
    real_sample_path.write_text("demo", encoding="utf-8")

    async with session_factory() as session:
        session.add(
            FieldMappingTemplate(
                platform="shopee",
                data_domain="products",
                granularity="daily",
                sub_domain=None,
                template_name="shopee_products__daily_v1",
                version=1,
                status="published",
                header_row=0,
                header_columns=["商品编号", "商品交易总额"],
                created_at=now,
                updated_at=now,
            )
        )
        session.add_all(
            [
                CatalogFile(
                    file_path="temp/development/shopee_products_daily_20250128_case3.xlsx",
                    file_name="shopee_products_daily_20250128_case3.xlsx",
                    source="data/raw",
                    platform_code="shopee",
                    source_platform="shopee",
                    data_domain="products",
                    granularity="daily",
                    status="pending",
                    first_seen_at=now,
                ),
                CatalogFile(
                    file_path=str(real_sample_path),
                    file_name=real_sample_path.name,
                    source="data/raw",
                    platform_code="shopee",
                    source_platform="shopee",
                    data_domain="products",
                    granularity="daily",
                    status="ingested",
                    first_seen_at=now,
                ),
            ]
        )
        await session.commit()

    response = await client.get("/api/data-sync/governance/detailed-coverage")

    assert response.status_code == 200
    coverage = response.json()["data"]
    assert coverage["covered"][0]["sample_file_name"] == "shopee_products_daily_real.xlsx"
