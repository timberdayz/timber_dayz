from datetime import datetime, timezone
import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
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
from backend.services.template_family_service import _variant_matches_sample_rows


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


def test_template_variant_sample_match_distinguishes_dash_and_slash_date_ranges():
    sample_rows = [{"date_period": "01-04-2026 - 30-04-2026"}]

    assert _variant_matches_sample_rows(
        [
            {
                "target_field": "metric_date",
                "source_column": "date_period",
                "value_kind": "date_range",
                "date_format": "dd-mm-yyyy-dd-mm-yyyy",
                "range_pick": "start",
            }
        ],
        sample_rows,
    )
    assert not _variant_matches_sample_rows(
        [
            {
                "target_field": "metric_date",
                "source_column": "date_period",
                "value_kind": "date_range",
                "date_format": "dd/mm/yyyy-dd/mm/yyyy",
                "range_pick": "start",
            }
        ],
        sample_rows,
    )


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
    assert family["current_file_count"] == 1
    assert family["pending_file_count"] == 1
    assert family["historical_file_count"] == 1

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


@pytest.mark.asyncio
async def test_template_resolve_uses_selected_variant_bindings_not_active_version(
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
                    template_name="shopee_analytics__monthly_slash_v3",
                    version=3,
                    status="published",
                    field_count=2,
                    header_columns=["slash_date", "GMV"],
                    deduplication_fields=["metric_date"],
                    header_bindings=[
                        {
                            "raw_name": "slash_date",
                            "display_name": "slash_date",
                            "semantic_key": "metric_date",
                            "semantic_review_status": "confirmed_semantic",
                            "hash_participates": True,
                        }
                    ],
                    field_parse_rules=[
                        {
                            "target_field": "metric_date",
                            "source_column": "slash_date",
                            "value_kind": "single_date",
                            "date_format": "dd/mm/yyyy",
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
                    template_name="shopee_analytics__monthly_dash_v4",
                    version=4,
                    status="published",
                    field_count=2,
                    header_columns=["dash_date", "GMV"],
                    deduplication_fields=["order_id"],
                    header_bindings=[
                        {
                            "raw_name": "dash_date",
                            "display_name": "dash_date",
                            "semantic_key": "order_id",
                            "semantic_review_status": "confirmed_semantic",
                            "hash_participates": True,
                        }
                    ],
                    field_parse_rules=[
                        {
                            "target_field": "metric_date",
                            "source_column": "dash_date",
                            "value_kind": "single_date",
                            "date_format": "dd-mm-yyyy",
                            "strict": True,
                        }
                    ],
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        await session.commit()

    response = await client.post(
        "/api/field-mapping/template-resolve",
        json={
            "platform": "shopee",
            "data_domain": "analytics",
            "granularity": "monthly",
            "header_columns": ["slash_date", "GMV"],
            "sample_rows": [{"slash_date": "01/03/2026", "GMV": "100"}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["variant"]["template_name"] == "shopee_analytics__monthly_slash_v3"
    assert payload["data"]["active_version"]["version_no"] == 4
    assert payload["data"]["semantic_bindings"][0]["raw_name"] == "slash_date"
    assert payload["data"]["hash_participating_semantic_keys"] == ["metric_date"]


@pytest.mark.asyncio
async def test_template_family_projection_keeps_distinct_variants_with_same_header_row(
    template_family_client,
):
    client, session_factory = template_family_client
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        session.add_all(
            [
                FieldMappingTemplate(
                    id=1,
                    platform="tiktok",
                    data_domain="analytics",
                    granularity="daily",
                    sub_domain=None,
                    header_row=7,
                    template_name="tiktok_analytics__daily_v7",
                    version=7,
                    status="published",
                    field_count=28,
                    header_columns=[
                        "Unnamed: 0", "GMV", "订单数", "客户数", "商品成交件数", "已退款的商品件数",
                        "SKU 订单数", "总成交额", "页面浏览次数", "商品访客数", "转化率", "商品曝光次数",
                        "去重商品曝光次数", "商品点击量", "去重点击次数", "平均订单金额", "达人直播归因 GMV",
                    ],
                    deduplication_fields=["metric_date"],
                    created_at=now,
                    updated_at=now,
                ),
                FieldMappingTemplate(
                    id=2,
                    platform="tiktok",
                    data_domain="analytics",
                    granularity="daily",
                    sub_domain="N/A",
                    header_row=7,
                    template_name="tiktok_analytics_N/A_daily_v2",
                    version=2,
                    status="published",
                    field_count=16,
                    header_columns=[
                        "Unnamed: 0", "GMV", "订单数", "客户数", "商品成交件数", "已退款的商品件数",
                        "SKU 订单数", "总成交额", "页面浏览次数", "商品访客数", "转化率", "商品曝光次数",
                        "去重商品曝光次数", "商品点击量", "去重点击次数", "平均订单金额",
                    ],
                    deduplication_fields=["metric_date"],
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        await session.commit()

    response = await client.get("/api/field-mapping/template-families")
    assert response.status_code == 200
    payload = response.json()
    families = payload["data"]["families"]
    family = next(
        item
        for item in families
        if item["platform"] == "tiktok" and item["data_domain"] == "analytics" and item["granularity"] == "daily"
    )

    version_response = await client.get(
        f"/api/field-mapping/template-families/{family['id']}/versions"
    )
    version_id = version_response.json()["data"]["versions"][0]["id"]

    variant_response = await client.get(
        f"/api/field-mapping/template-versions/{version_id}/variants"
    )
    assert variant_response.status_code == 200
    variants = variant_response.json()["data"]["variants"]
    assert len(variants) == 2
    assert len({item["variant_key"] for item in variants}) == 2
    assert {item["source_legacy_template_id"] for item in variants} == {1, 2}


@pytest.mark.asyncio
async def test_template_family_list_tolerates_duplicate_family_rows(template_family_client):
    client, session_factory = template_family_client
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        session.add_all(
            [
                FieldMappingTemplateFamily(
                    id=101,
                    platform="shopee",
                    data_domain="analytics",
                    granularity="monthly",
                    sub_domain=None,
                    account=None,
                    governance_status="ready",
                    display_name="duplicate-a",
                    created_at=now,
                    updated_at=now,
                ),
                FieldMappingTemplateFamily(
                    id=102,
                    platform="shopee",
                    data_domain="analytics",
                    granularity="monthly",
                    sub_domain=None,
                    account=None,
                    governance_status="ready",
                    display_name="duplicate-b",
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        await session.commit()

    response = await client.get("/api/field-mapping/template-families")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["count"] == 1


@pytest.mark.asyncio
async def test_get_family_versions_uses_requested_family_when_normalized_duplicate_is_listed(
    template_family_client,
):
    _client, session_factory = template_family_client
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        session.add_all(
            [
                FieldMappingTemplateFamily(
                    id=201,
                    platform="tiktok",
                    data_domain="analytics",
                    granularity="daily",
                    sub_domain=None,
                    account=None,
                    governance_status="ready",
                    display_name="tiktok analytics daily",
                    active_version_id=301,
                    created_at=now,
                    updated_at=now,
                ),
                FieldMappingTemplateVersion(
                    id=301,
                    family_id=201,
                    version_no=8,
                    status="active",
                    template_name="tiktok_analytics__daily_v8",
                    deduplication_fields=["metric_date"],
                    header_bindings=[],
                    created_at=now,
                    updated_at=now,
                ),
                FieldMappingTemplateFamily(
                    id=202,
                    platform="tiktok",
                    data_domain="analytics",
                    granularity="daily",
                    sub_domain="N/A",
                    account=None,
                    governance_status="ready",
                    display_name="tiktok analytics N/A daily",
                    active_version_id=302,
                    created_at=now,
                    updated_at=now,
                ),
                FieldMappingTemplateVersion(
                    id=302,
                    family_id=202,
                    version_no=2,
                    status="active",
                    template_name="tiktok_analytics_N/A_daily_v2",
                    deduplication_fields=["metric_date"],
                    header_bindings=[],
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        await session.commit()

        from backend.services.template_family_service import TemplateFamilyService

        family_payload, versions = await TemplateFamilyService(session).get_family_versions(201)

    assert family_payload["id"] == 201
    assert family_payload["sub_domain"] is None
    assert versions[0]["id"] == 301


@pytest.mark.asyncio
async def test_template_family_list_prefers_canonical_null_over_na_duplicate(
    template_family_client,
):
    _client, session_factory = template_family_client
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        session.add_all(
            [
                FieldMappingTemplateFamily(
                    id=211,
                    platform="tiktok",
                    data_domain="analytics",
                    granularity="daily",
                    sub_domain=None,
                    account=None,
                    governance_status="ready",
                    display_name="canonical-null",
                    active_version_id=311,
                    created_at=now,
                    updated_at=now,
                ),
                FieldMappingTemplateVersion(
                    id=311,
                    family_id=211,
                    version_no=8,
                    status="active",
                    template_name="tiktok_analytics__daily_v8",
                    deduplication_fields=["metric_date"],
                    header_bindings=[],
                    created_at=now,
                    updated_at=now,
                ),
                FieldMappingTemplateFamily(
                    id=212,
                    platform="tiktok",
                    data_domain="analytics",
                    granularity="daily",
                    sub_domain="N/A",
                    account=None,
                    governance_status="ready",
                    display_name="legacy-na",
                    active_version_id=312,
                    created_at=now,
                    updated_at=now,
                ),
                FieldMappingTemplateVersion(
                    id=312,
                    family_id=212,
                    version_no=2,
                    status="active",
                    template_name="tiktok_analytics_N/A_daily_v2",
                    deduplication_fields=["metric_date"],
                    header_bindings=[],
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        await session.commit()

        from backend.services.template_family_service import TemplateFamilyService

        families = await TemplateFamilyService(session).list_families(
            platform="tiktok",
            data_domain="analytics",
        )

    daily_family = next(item for item in families if item["granularity"] == "daily")
    assert daily_family["id"] == 211
    assert daily_family["sub_domain"] is None


@pytest.mark.asyncio
async def test_projection_ignores_cross_dimension_templates_when_building_variants(
    template_family_client,
):
    _client, session_factory = template_family_client
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        tiktok_template = FieldMappingTemplate(
            id=401,
            platform="tiktok",
            data_domain="orders",
            granularity="monthly",
            sub_domain=None,
            header_row=1,
            template_name="tiktok_orders__monthly_v5",
            version=5,
            status="published",
            field_count=3,
            header_columns=["订单编号", "订单状态", "付款时间"],
            deduplication_fields=["order_id"],
            created_at=now,
            updated_at=now,
        )
        shopee_template = FieldMappingTemplate(
            id=402,
            platform="shopee",
            data_domain="orders",
            granularity="daily",
            sub_domain=None,
            header_row=1,
            template_name="shopee_orders__daily_v2",
            version=2,
            status="published",
            field_count=3,
            header_columns=["订单编号", "订单状态", "付款时间"],
            deduplication_fields=["order_id"],
            created_at=now,
            updated_at=now,
        )
        session.add_all([tiktok_template, shopee_template])
        await session.commit()

        from backend.services.template_family_service import TemplateFamilyService

        service = TemplateFamilyService(session)
        await service._upsert_projection_group(
            ("tiktok", "orders", None, "monthly", None),
            [tiktok_template, shopee_template],
        )
        await session.commit()

        variants_result = await session.execute(
            select(FieldMappingTemplateVariant).order_by(FieldMappingTemplateVariant.id)
        )
        variants = list(variants_result.scalars().all())

    assert [variant.source_legacy_template_id for variant in variants] == [401]
