from datetime import datetime, timezone
import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from modules.core.db import (
    CatalogFile,
    FieldMappingTemplate,
    FieldMappingTemplateFamily,
    FieldMappingTemplateVariant,
    FieldMappingTemplateVersion,
)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest_asyncio.fixture
async def template_family_client():
    from backend.main import app
    from backend.models.database import get_async_db

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS core"))
        await conn.run_sync(CatalogFile.__table__.create)
        await conn.run_sync(FieldMappingTemplate.__table__.create)
        await conn.run_sync(FieldMappingTemplateFamily.__table__.create)
        await conn.run_sync(FieldMappingTemplateVersion.__table__.create)
        await conn.run_sync(FieldMappingTemplateVariant.__table__.create)

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
async def test_template_family_endpoints_group_legacy_templates_into_variants(
    template_family_client,
):
    client, session_factory = template_family_client
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        session.add_all(
            [
                FieldMappingTemplate(
                    platform="shopee",
                    data_domain="analytics",
                    granularity="monthly",
                    sub_domain=None,
                    header_row=3,
                    template_name="shopee_analytics__monthly_dash_v2",
                    version=2,
                    status="published",
                    field_count=3,
                    header_columns=["日期", "浏览量", "访客数"],
                    deduplication_fields=["日期"],
                    field_parse_rules=[
                        {
                            "target_field": "metric_date",
                            "source_column": "日期",
                            "value_kind": "single_date",
                            "date_format": "dd-mm-yyyy",
                            "strict": True,
                        }
                    ],
                    created_at=now,
                    updated_at=now,
                ),
                FieldMappingTemplate(
                    platform="shopee",
                    data_domain="analytics",
                    granularity="monthly",
                    sub_domain=None,
                    header_row=3,
                    template_name="shopee_analytics__monthly_slash_v3",
                    version=3,
                    status="published",
                    field_count=3,
                    header_columns=["日期", "浏览量", "访客数"],
                    deduplication_fields=["日期"],
                    field_parse_rules=[
                        {
                            "target_field": "metric_date",
                            "source_column": "日期",
                            "value_kind": "single_date",
                            "date_format": "dd/mm/yyyy",
                            "strict": True,
                        }
                    ],
                    created_at=now,
                    updated_at=now,
                ),
                CatalogFile(
                    file_path="data/raw/shopee/analytics/monthly_demo.xlsx",
                    file_name="monthly_demo.xlsx",
                    source="data/raw",
                    platform_code="shopee",
                    source_platform="shopee",
                    data_domain="analytics",
                    granularity="monthly",
                    status="pending",
                    first_seen_at=now,
                ),
            ]
        )
        await session.commit()

    response = await client.get("/api/field-mapping/template-families")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["count"] == 1

    family = payload["data"]["families"][0]
    assert family["platform"] == "shopee"
    assert family["data_domain"] == "analytics"
    assert family["granularity"] == "monthly"
    assert family["variant_count"] == 2
    assert family["active_version"]["version_no"] == 3
    assert family["governance_status"] == "ready"

    version_response = await client.get(
        f"/api/field-mapping/template-families/{family['id']}/versions"
    )
    assert version_response.status_code == 200
    version_payload = version_response.json()
    assert version_payload["success"] is True
    assert version_payload["data"]["versions"][0]["variant_count"] == 2

    version_id = version_payload["data"]["versions"][0]["id"]
    variant_response = await client.get(
        f"/api/field-mapping/template-versions/{version_id}/variants"
    )
    assert variant_response.status_code == 200
    variant_payload = variant_response.json()
    assert variant_payload["success"] is True
    assert len(variant_payload["data"]["variants"]) == 2
    variant_keys = {item["variant_key"] for item in variant_payload["data"]["variants"]}
    assert {"monthly_dash", "monthly_slash"} == variant_keys


@pytest.mark.asyncio
async def test_template_resolve_endpoint_matches_variant_and_reports_shadow_compare(
    template_family_client,
    monkeypatch,
):
    client, session_factory = template_family_client
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        session.add_all(
            [
                FieldMappingTemplate(
                    platform="shopee",
                    data_domain="analytics",
                    granularity="monthly",
                    sub_domain=None,
                    header_row=3,
                    template_name="shopee_analytics__monthly_dash_v2",
                    version=2,
                    status="published",
                    field_count=3,
                    header_columns=["日期", "浏览量", "访客数"],
                    deduplication_fields=["日期"],
                    field_parse_rules=[
                        {
                            "target_field": "metric_date",
                            "source_column": "日期",
                            "value_kind": "single_date",
                            "date_format": "dd-mm-yyyy",
                            "strict": True,
                        }
                    ],
                    created_at=now,
                    updated_at=now,
                ),
                FieldMappingTemplate(
                    platform="shopee",
                    data_domain="analytics",
                    granularity="monthly",
                    sub_domain=None,
                    header_row=3,
                    template_name="shopee_analytics__monthly_slash_v3",
                    version=3,
                    status="published",
                    field_count=3,
                    header_columns=["日期", "浏览量", "访客数"],
                    deduplication_fields=["日期"],
                    field_parse_rules=[
                        {
                            "target_field": "metric_date",
                            "source_column": "日期",
                            "value_kind": "single_date",
                            "date_format": "dd/mm/yyyy",
                            "strict": True,
                        }
                    ],
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        await session.commit()

    from backend.domains.data_platform.routers import field_mapping_templates as router_module

    monkeypatch.setattr(
        router_module,
        "_load_file_update_preview",
        lambda *_args, **_kwargs: None,
        raising=False,
    )

    response = await client.post(
        "/api/field-mapping/template-resolve",
        json={
            "platform": "shopee",
            "data_domain": "analytics",
            "granularity": "monthly",
            "header_columns": ["日期", "浏览量", "访客数"],
            "sample_rows": [{"日期": "01/03/2026", "浏览量": "100", "访客数": "20"}],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["matched"] is True
    assert payload["data"]["variant"]["variant_key"] == "monthly_slash"
    assert payload["data"]["active_version"]["version_no"] == 3
    assert payload["data"]["shadow_compare"]["legacy_template_name"] == "shopee_analytics__monthly_slash_v3"
    assert payload["data"]["shadow_compare"]["is_consistent"] is True
