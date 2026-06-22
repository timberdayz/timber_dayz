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


def test_orders_template_header_normalization_preserves_rmb_suffixes():
    from backend.routers.field_mapping_templates import _normalize_template_headers_for_domain

    normalized = _normalize_template_headers_for_domain(
        data_domain="orders",
        header_columns=["订单编号", "利润", "利润(RMB)", "买家支付(RMB)"],
    )

    assert normalized == ["订单编号", "利润", "利润(RMB)", "买家支付(RMB)"]


def test_non_orders_template_header_normalization_preserves_raw_headers_for_template_storage():
    from backend.routers.field_mapping_templates import _normalize_template_headers_for_domain

    normalized = _normalize_template_headers_for_domain(
        data_domain="products",
        header_columns=["利润(RMB)"],
    )

    assert normalized == ["利润(RMB)"]


def test_confirmed_non_semantic_binding_is_not_returned_for_manual_review():
    from backend.routers.field_mapping_templates import _filter_bindings_for_manual_review

    bindings = [
        {
            "raw_name": "商品名",
            "display_name": "商品名",
            "semantic_key": None,
            "semantic_review_status": "confirmed_non_semantic",
            "hash_participates": False,
        },
        {
            "raw_name": "商品 ID",
            "display_name": "商品 ID",
            "semantic_key": "product_id",
            "semantic_review_status": "confirmed_semantic",
            "hash_participates": True,
        },
        {
            "raw_name": "发品状态",
            "display_name": "发品状态",
            "semantic_key": None,
            "semantic_review_status": "pending",
            "hash_participates": True,
            "hash_eligible": True,
        },
    ]

    filtered = _filter_bindings_for_manual_review(bindings)

    assert [item["raw_name"] for item in filtered] == ["发品状态"]


def test_manual_review_filter_excludes_ordinary_pending_raw_fields():
    from backend.routers.field_mapping_templates import _filter_bindings_for_manual_review

    bindings = [
        {
            "raw_name": "ordinary_raw_column",
            "display_name": "ordinary_raw_column",
            "semantic_key": None,
            "semantic_review_status": "pending",
            "hash_participates": False,
            "required": False,
            "hash_eligible": False,
        },
        {
            "raw_name": "identity_candidate",
            "display_name": "identity_candidate",
            "semantic_key": None,
            "semantic_review_status": "pending",
            "hash_participates": True,
            "required": False,
            "hash_eligible": True,
        },
    ]

    filtered = _filter_bindings_for_manual_review(bindings)

    assert [item["raw_name"] for item in filtered] == ["identity_candidate"]


def test_existing_deduplication_fields_match_by_semantic_key_without_raw_header_match():
    from backend.routers.field_mapping_templates import _split_existing_deduplication_fields

    available, missing, matches = _split_existing_deduplication_fields(
        ["商品", "状态"],
        ["商品名称", "发品状态"],
        [
            {
                "raw_name": "商品名称",
                "semantic_key": "product_name",
                "semantic_review_status": "confirmed_semantic",
            },
            {
                "raw_name": "发品状态",
                "semantic_key": "item_status",
                "semantic_review_status": "confirmed_semantic",
            },
        ],
        existing_header_bindings=[
            {
                "raw_name": "商品",
                "semantic_key": "product_name",
                "semantic_review_status": "confirmed_semantic",
            },
            {
                "raw_name": "状态",
                "semantic_key": "item_status",
                "semantic_review_status": "confirmed_semantic",
            },
        ],
    )

    assert available == ["product_name"]
    assert missing == []
    assert matches == [
        {
            "requested_field": "商品",
            "semantic_key": "product_name",
            "current_field": "商品名称",
            "match_type": "semantic_key",
            "hash_eligible": True,
            "status": "matched_hashable",
        },
        {
            "requested_field": "状态",
            "semantic_key": "item_status",
            "current_field": "发品状态",
            "match_type": "semantic_key",
            "hash_eligible": False,
            "status": "matched_non_hashable",
        },
    ]


@pytest_asyncio.fixture
async def template_update_context_client():
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
async def test_template_update_context_returns_lightweight_summary_for_with_sample(
    template_update_context_client,
    monkeypatch,
):
    client, session_factory = template_update_context_client

    async with session_factory() as session:
        template = FieldMappingTemplate(
            platform="shopee",
            data_domain="orders",
            granularity="daily",
            sub_domain=None,
            header_row=1,
            header_columns=["order_id", "platform_sku", "amount", "shop_id"],
            deduplication_fields=["order_id", "shop_id"],
            template_name="shopee_orders_daily_v1",
            version=1,
            status="published",
            field_count=4,
            created_by="test",
        )
        file_record = CatalogFile(
            file_path="data/raw/shopee/orders/orders_daily_demo.xlsx",
            file_name="orders_daily_demo.xlsx",
            source="data/raw",
            platform_code="shopee",
            source_platform="shopee",
            data_domain="orders",
            granularity="daily",
            status="pending",
            first_seen_at=datetime.now(timezone.utc),
        )
        session.add(template)
        session.add(file_record)
        await session.commit()
        await session.refresh(template)
        await session.refresh(file_record)

    from backend.routers import field_mapping_templates as router_module

    async def fake_load_file_update_summary(db, file_id, header_row):
        assert file_id == file_record.id
        assert header_row == expected_header_row
        return {
            "file": {
                "id": file_record.id,
                "file_name": file_record.file_name,
                "platform": "shopee",
                "domain": "orders",
                "granularity": "daily",
                "sub_domain": None,
            },
            "header_columns": ["order_id", "amount", "platform_sku", "new_metric"],
            "header_bindings": [
                {
                    "raw_name": "order_id",
                    "display_name": "order_id",
                    "semantic_key": "order_id",
                    "semantic_role": None,
                    "aliases": ["order_id"],
                    "required": True,
                    "hash_participates": True,
                    "position": 0,
                    "sample_type": "string",
                    "confidence": 0.9,
                },
                {
                    "raw_name": "new_metric",
                    "display_name": "new_metric",
                    "semantic_key": None,
                    "semantic_role": None,
                    "aliases": [],
                    "required": False,
                    "hash_participates": False,
                    "position": 3,
                    "sample_type": "number",
                    "confidence": 0.7,
                },
            ],
        }

    monkeypatch.setattr(
        router_module,
        "_load_file_update_summary",
        fake_load_file_update_summary,
        raising=False,
    )

    expected_header_row = 3
    response = await client.get(
        f"/api/field-mapping/templates/{template.id}/update-context",
        params={"file_id": file_record.id, "header_row": expected_header_row},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True

    data = payload["data"]
    assert data["template"]["id"] == template.id
    assert data["template"]["template_name"] == "shopee_orders_daily_v1"
    assert data["template"]["deduplication_fields"] == ["order_id", "shop_id"]
    assert data["template_header_columns"] == ["order_id", "platform_sku", "amount", "shop_id"]
    assert data["current_file"]["id"] == file_record.id
    assert data["current_file"]["file_name"] == file_record.file_name
    assert data["current_header_columns"] == ["order_id", "amount", "platform_sku", "new_metric"]
    assert data["current_header_row"] == expected_header_row
    assert data["preview_data"] == []
    assert data["sample_data"] == {}
    assert data["header_changes"]["detected"] is True
    assert data["added_fields"] == ["new_metric"]
    assert data["removed_fields"] == ["shop_id"]
    assert data["existing_deduplication_fields_available"] == ["order_id"]
    assert data["existing_deduplication_fields_missing"] == ["shop_id"]
    assert data["recommended_deduplication_fields"] == ["order_id"]
    assert data["review_header_bindings"] == []
    full_bindings_by_raw = {item["raw_name"]: item for item in data["full_header_bindings"]}
    assert full_bindings_by_raw["order_id"]["semantic_key"] == "order_id"
    assert full_bindings_by_raw["order_id"]["semantic_review_status"] == "confirmed_semantic"
    assert full_bindings_by_raw["new_metric"]["semantic_review_status"] == "pending"
    assert data["current_header_bindings"] == data["full_header_bindings"]
    assert data["update_mode"] == "with-sample"


@pytest.mark.asyncio
async def test_template_update_context_returns_semantic_equivalent_deduplication_matches(
    template_update_context_client,
    monkeypatch,
):
    client, session_factory = template_update_context_client

    async with session_factory() as session:
        template = FieldMappingTemplate(
            platform="shopee",
            data_domain="products",
            granularity="daily",
            sub_domain=None,
            header_row=0,
            header_columns=["商品", "状态", "浏览量"],
            deduplication_fields=["商品", "状态"],
            header_bindings=[
                {
                    "raw_name": "商品",
                    "display_name": "商品",
                    "semantic_key": "product_name",
                    "semantic_review_status": "confirmed_semantic",
                },
                {
                    "raw_name": "状态",
                    "display_name": "状态",
                    "semantic_key": "item_status",
                    "semantic_review_status": "confirmed_semantic",
                },
            ],
            template_name="shopee_products_daily_legacy_product_name",
            version=1,
            status="published",
            field_count=3,
            created_by="test",
        )
        file_record = CatalogFile(
            file_path="data/raw/shopee/products/products_daily_demo.xlsx",
            file_name="products_daily_demo.xlsx",
            source="data/raw",
            platform_code="shopee",
            source_platform="shopee",
            data_domain="products",
            granularity="daily",
            status="pending",
            first_seen_at=datetime.now(timezone.utc),
        )
        session.add(template)
        session.add(file_record)
        await session.commit()
        await session.refresh(template)
        await session.refresh(file_record)

    from backend.routers import field_mapping_templates as router_module

    async def fake_load_file_update_summary(*_, **__):
        return {
            "file": {
                "id": file_record.id,
                "file_name": file_record.file_name,
                "platform": "shopee",
                "domain": "products",
                "granularity": "daily",
                "sub_domain": None,
            },
            "header_columns": ["商品名称", "发品状态", "浏览量"],
            "header_bindings": [
                {
                    "raw_name": "商品名称",
                    "display_name": "商品名称",
                    "semantic_key": "product_name",
                    "semantic_review_status": "confirmed_semantic",
                    "position": 0,
                },
                {
                    "raw_name": "发品状态",
                    "display_name": "发品状态",
                    "semantic_key": "item_status",
                    "semantic_review_status": "confirmed_semantic",
                    "position": 1,
                },
            ],
        }

    monkeypatch.setattr(
        router_module,
        "_load_file_update_summary",
        fake_load_file_update_summary,
        raising=False,
    )

    response = await client.get(
        f"/api/field-mapping/templates/{template.id}/update-context",
        params={"mode": "with-sample", "file_id": file_record.id},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["existing_deduplication_fields_available"] == ["product_name", "item_status"]
    assert data["existing_deduplication_fields_missing"] == []
    assert data["existing_deduplication_field_matches"] == [
        {
            "requested_field": "商品",
            "semantic_key": "product_name",
            "current_field": "商品名称",
            "match_type": "semantic_key",
            "hash_eligible": True,
            "status": "matched_hashable",
        },
        {
            "requested_field": "状态",
            "semantic_key": "item_status",
            "current_field": "发品状态",
            "match_type": "semantic_key",
            "hash_eligible": True,
            "status": "matched_hashable",
        },
    ]


@pytest.mark.asyncio
async def test_template_update_context_returns_backend_hash_options_for_item_status(
    template_update_context_client,
    monkeypatch,
):
    client, session_factory = template_update_context_client

    async with session_factory() as session:
        template = FieldMappingTemplate(
            platform="shopee",
            data_domain="products",
            granularity="daily",
            sub_domain=None,
            header_row=0,
            header_columns=["商品", "状态", "浏览量"],
            deduplication_fields=["商品", "状态"],
            header_bindings=[
                {
                    "raw_name": "商品",
                    "display_name": "商品",
                    "semantic_key": "product_name",
                    "semantic_review_status": "confirmed_semantic",
                },
                {
                    "raw_name": "状态",
                    "display_name": "状态",
                    "semantic_key": "item_status",
                    "semantic_review_status": "confirmed_semantic",
                },
            ],
            template_name="shopee_products_daily_legacy_status_hash",
            version=1,
            status="published",
            field_count=3,
            created_by="test",
        )
        file_record = CatalogFile(
            file_path="data/raw/shopee/products/products_daily_status_demo.xlsx",
            file_name="products_daily_status_demo.xlsx",
            source="data/raw",
            platform_code="shopee",
            source_platform="shopee",
            data_domain="products",
            granularity="daily",
            status="pending",
            first_seen_at=datetime.now(timezone.utc),
        )
        session.add_all([template, file_record])
        await session.commit()
        await session.refresh(template)
        await session.refresh(file_record)

    from backend.routers import field_mapping_templates as router_module

    async def fake_load_file_update_summary(*_, **__):
        return {
            "file": {
                "id": file_record.id,
                "file_name": file_record.file_name,
                "platform": "shopee",
                "domain": "products",
                "granularity": "daily",
                "sub_domain": None,
            },
            "header_columns": ["商品 ID", "商品名称", "发品状态", "GMV"],
            "header_bindings": [
                {
                    "raw_name": "商品 ID",
                    "display_name": "商品 ID",
                    "semantic_key": "product_id",
                    "semantic_review_status": "confirmed_semantic",
                    "position": 0,
                },
                {
                    "raw_name": "商品名称",
                    "display_name": "商品名称",
                    "semantic_key": "product_name",
                    "semantic_review_status": "confirmed_semantic",
                    "position": 1,
                },
                {
                    "raw_name": "发品状态",
                    "display_name": "发品状态",
                    "semantic_key": "item_status",
                    "semantic_review_status": "confirmed_semantic",
                    "position": 2,
                },
                {
                    "raw_name": "GMV",
                    "display_name": "GMV",
                    "semantic_key": "gmv",
                    "semantic_review_status": "confirmed_semantic",
                    "position": 3,
                },
            ],
        }

    monkeypatch.setattr(
        router_module,
        "_load_file_update_summary",
        fake_load_file_update_summary,
        raising=False,
    )

    response = await client.get(
        f"/api/field-mapping/templates/{template.id}/update-context",
        params={"mode": "with-sample", "file_id": file_record.id},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["existing_deduplication_fields_available"] == ["product_name", "item_status"]
    assert data["existing_deduplication_fields_missing"] == []
    by_key = {option["semantic_key"]: option for option in data["hash_options"]}
    assert by_key["product_id"]["eligible"] is True
    assert by_key["product_id"]["recommended"] is True
    assert by_key["item_status"]["eligible"] is True
    assert by_key["item_status"]["weak_identity"] is True
    assert by_key["item_status"]["legacy_compatible"] is True
    assert by_key["gmv"]["eligible"] is False
    assert by_key["gmv"]["blocked_reason"]


@pytest.mark.asyncio
async def test_template_update_context_core_only_uses_template_headers_as_field_pool(
    template_update_context_client,
):
    client, session_factory = template_update_context_client

    async with session_factory() as session:
        template = FieldMappingTemplate(
            platform="shopee",
            data_domain="orders",
            granularity="daily",
            sub_domain=None,
            header_row=1,
            header_columns=["order_id", "platform_sku", "amount", "shop_id"],
            deduplication_fields=["order_id", "missing_field"],
            template_name="shopee_orders_daily_v2",
            version=2,
            status="published",
            field_count=4,
            created_by="test",
        )
        session.add(template)
        await session.commit()
        await session.refresh(template)

    response = await client.get(
        f"/api/field-mapping/templates/{template.id}/update-context",
        params={"mode": "core-only"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True

    data = payload["data"]
    assert data["template"]["id"] == template.id
    assert data["template_header_columns"] == [
        "order_id",
        "platform_sku",
        "amount",
        "shop_id",
    ]
    assert data["current_header_columns"] == [
        "order_id",
        "platform_sku",
        "amount",
        "shop_id",
    ]
    assert data["current_file"] is None
    assert data["preview_data"] == []
    assert data["sample_data"] == {}
    assert data["added_fields"] == []
    assert data["removed_fields"] == []
    assert data["match_rate"] == 100.0
    assert data["update_mode"] == "core-only"
    assert data["current_header_row"] == 1
    assert data["header_source"] == "template"
    assert data["existing_deduplication_fields_available"] == ["order_id"]
    assert data["existing_deduplication_fields_missing"] == ["missing_field"]
    assert data["recommended_deduplication_fields"] == ["order_id"]


@pytest.mark.asyncio
async def test_template_update_preview_returns_preview_payload(
    template_update_context_client,
    monkeypatch,
):
    client, session_factory = template_update_context_client

    async with session_factory() as session:
        template = FieldMappingTemplate(
            platform="shopee",
            data_domain="orders",
            granularity="daily",
            sub_domain=None,
            header_row=2,
            header_columns=["order_id", "amount"],
            deduplication_fields=["order_id"],
            template_name="shopee_orders_daily_preview_v1",
            version=1,
            status="published",
            field_count=2,
            created_by="test",
        )
        file_record = CatalogFile(
            file_path="data/raw/shopee/orders/orders_preview_demo.xlsx",
            file_name="orders_preview_demo.xlsx",
            source="data/raw",
            platform_code="shopee",
            source_platform="shopee",
            data_domain="orders",
            granularity="daily",
            status="pending",
            first_seen_at=datetime.now(timezone.utc),
        )
        session.add_all([template, file_record])
        await session.commit()
        await session.refresh(template)
        await session.refresh(file_record)

    from backend.routers import field_mapping_templates as router_module

    async def fake_load_file_update_preview(db, file_id, header_row):
        assert file_id == file_record.id
        assert header_row == 4
        return {
            "file": {
                "id": file_record.id,
                "file_name": file_record.file_name,
                "platform": "shopee",
                "domain": "orders",
                "granularity": "daily",
                "sub_domain": None,
            },
            "header_columns": ["order_id", "amount"],
            "sample_data": {"order_id": "SO-1", "amount": "9.9"},
            "preview_data": [{"order_id": "SO-1", "amount": "9.9"}],
            "header_bindings": [],
        }

    monkeypatch.setattr(router_module, "_load_file_update_preview", fake_load_file_update_preview, raising=False)

    response = await client.get(
        f"/api/field-mapping/templates/{template.id}/update-preview",
        params={"file_id": file_record.id, "header_row": 4},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["current_file"]["id"] == file_record.id
    assert payload["data"]["current_header_columns"] == ["order_id", "amount"]
    assert payload["data"]["sample_data"]["order_id"] == "SO-1"
    assert payload["data"]["preview_data"][0]["amount"] == "9.9"


@pytest.mark.asyncio
async def test_template_update_bindings_returns_full_bindings_payload(
    template_update_context_client,
    monkeypatch,
):
    client, session_factory = template_update_context_client

    async with session_factory() as session:
        template = FieldMappingTemplate(
            platform="shopee",
            data_domain="orders",
            granularity="daily",
            sub_domain=None,
            header_row=1,
            header_columns=["order_id", "metric_date", "amount"],
            deduplication_fields=["order_id", "metric_date"],
            template_name="shopee_orders_daily_bindings_v1",
            version=1,
            status="published",
            field_count=3,
            created_by="test",
        )
        file_record = CatalogFile(
            file_path="data/raw/shopee/orders/orders_bindings_demo.xlsx",
            file_name="orders_bindings_demo.xlsx",
            source="data/raw",
            platform_code="shopee",
            source_platform="shopee",
            data_domain="orders",
            granularity="daily",
            status="pending",
            first_seen_at=datetime.now(timezone.utc),
        )
        session.add_all([template, file_record])
        await session.commit()
        await session.refresh(template)
        await session.refresh(file_record)

    from backend.routers import field_mapping_templates as router_module

    async def fake_load_file_update_preview(db, file_id, header_row):
        assert file_id == file_record.id
        assert header_row == 1
        return {
            "file": {
                "id": file_record.id,
                "file_name": file_record.file_name,
                "platform": "shopee",
                "domain": "orders",
                "granularity": "daily",
                "sub_domain": None,
            },
            "header_columns": ["order_id", "Unnamed: 0", "amount"],
            "sample_data": {"order_id": "SO-1", "Unnamed: 0": "2026-06-07", "amount": "9.9"},
            "preview_data": [],
            "header_bindings": [
                {
                    "raw_name": "order_id",
                    "display_name": "order_id",
                    "semantic_key": "order_id",
                    "semantic_role": None,
                    "aliases": ["order_id"],
                    "required": True,
                    "hash_participates": True,
                    "position": 0,
                    "sample_type": "string",
                    "confidence": 0.9,
                },
                {
                    "raw_name": "Unnamed: 0",
                    "display_name": "日期",
                    "semantic_key": "metric_date",
                    "semantic_role": "metric_date",
                    "aliases": ["日期", "统计日期"],
                    "required": False,
                    "hash_participates": True,
                    "position": 1,
                    "sample_type": "date",
                    "confidence": 0.98,
                },
            ],
        }

    monkeypatch.setattr(router_module, "_load_file_update_preview", fake_load_file_update_preview, raising=False)

    response = await client.get(
        f"/api/field-mapping/templates/{template.id}/update-bindings",
        params={"file_id": file_record.id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert len(payload["data"]["current_header_bindings"]) == 3
    assert len(payload["data"]["full_header_bindings"]) == 3
    assert payload["data"]["review_header_bindings"] == []
    assert payload["data"]["required_semantic_keys"] == ["order_id"]
    assert payload["data"]["hash_participating_semantic_keys"] == ["order_id", "metric_date"]
    assert payload["data"]["full_header_bindings"][2]["raw_name"] == "amount"
    assert payload["data"]["full_header_bindings"][2]["semantic_review_status"] == "pending"


@pytest.mark.asyncio
async def test_template_update_context_with_sample_requires_file_id(
    template_update_context_client,
):
    client, session_factory = template_update_context_client

    async with session_factory() as session:
        template = FieldMappingTemplate(
            platform="shopee",
            data_domain="orders",
            granularity="daily",
            sub_domain=None,
            header_row=1,
            header_columns=["order_id", "amount"],
            deduplication_fields=["order_id"],
            template_name="shopee_orders_daily_v1",
            version=1,
            status="published",
            field_count=2,
            created_by="test",
        )
        session.add(template)
        await session.commit()
        await session.refresh(template)

    response = await client.get(
        f"/api/field-mapping/templates/{template.id}/update-context",
        params={"mode": "with-sample"},
    )

    assert response.status_code == 400
    assert "file_id" in response.text


@pytest.mark.asyncio
async def test_template_update_context_with_sample_requires_file_id(
    template_update_context_client,
):
    client, session_factory = template_update_context_client

    async with session_factory() as session:
        template = FieldMappingTemplate(
            platform="shopee",
            data_domain="orders",
            granularity="daily",
            sub_domain=None,
            header_row=1,
            header_columns=["order_id", "amount"],
            deduplication_fields=["order_id"],
            template_name="shopee_orders_daily_v1",
            version=1,
            status="published",
            field_count=2,
            created_by="test",
        )
        session.add(template)
        await session.commit()
        await session.refresh(template)

    response = await client.get(
        f"/api/field-mapping/templates/{template.id}/update-context",
        params={"mode": "with-sample"},
    )

    assert response.status_code == 400
    assert "file_id" in response.text


@pytest.mark.asyncio
async def test_variant_create_context_returns_active_version_and_sample_preview(
    template_update_context_client,
    monkeypatch,
):
    client, session_factory = template_update_context_client

    async with session_factory() as session:
        legacy_template = FieldMappingTemplate(
            id=801,
            platform="shopee",
            data_domain="analytics",
            granularity="monthly",
            sub_domain=None,
            header_row=3,
            header_columns=["日期", "浏览量"],
            deduplication_fields=["日期"],
            template_name="shopee_analytics__monthly_slash_v3",
            version=3,
            status="published",
            field_count=2,
            created_by="test",
        )
        family = FieldMappingTemplateFamily(
            id=901,
            platform="shopee",
            data_domain="analytics",
            granularity="monthly",
            sub_domain=None,
            display_name="shopee / analytics / default / monthly",
            governance_status="missing_variant",
        )
        version = FieldMappingTemplateVersion(
            id=902,
            family_id=901,
            version_no=3,
            status="active",
            template_name="shopee_analytics__monthly_slash_v3",
            deduplication_fields=["日期"],
            legacy_template_ids=[801],
            created_by="test",
        )
        variant = FieldMappingTemplateVariant(
            id=903,
            template_version_id=902,
            variant_key="monthly_slash",
            match_priority=1,
            header_row=3,
            required_headers=["日期", "浏览量"],
            parse_profile={"date_formats": ["dd/mm/yyyy"]},
            field_parse_rules=[
                {
                    "target_field": "metric_date",
                    "source_column": "日期",
                    "value_kind": "single_date",
                    "date_format": "dd/mm/yyyy",
                    "strict": True,
                }
            ],
            source_legacy_template_id=801,
            template_name="shopee_analytics__monthly_slash_v3",
        )
        family.active_version_id = 902
        file_record = CatalogFile(
            id=904,
            file_path="data/raw/shopee/analytics/monthly_demo.xlsx",
            file_name="monthly_demo.xlsx",
            source="data/raw",
            platform_code="shopee",
            source_platform="shopee",
            data_domain="analytics",
            granularity="monthly",
            status="pending",
            first_seen_at=datetime.now(timezone.utc),
        )
        session.add_all([legacy_template, family, version, variant, file_record])
        await session.commit()

    from backend.domains.data_platform.routers import field_mapping_templates as router_module

    async def fake_load_file_update_preview(db, file_id, header_row):
        assert file_id == 904
        assert header_row == 3
        return {
            "file": {
                "id": 904,
                "file_name": "monthly_demo.xlsx",
                "platform": "shopee",
                "domain": "analytics",
                "granularity": "monthly",
                "sub_domain": None,
            },
            "header_columns": ["日期", "浏览量"],
            "header_bindings": [],
            "sample_data": {"日期": "01/03/2026", "浏览量": "100"},
            "preview_data": [{"日期": "01/03/2026", "浏览量": "100"}],
        }

    monkeypatch.setattr(router_module, "_load_file_update_preview", fake_load_file_update_preview, raising=False)

    response = await client.get(
        "/api/field-mapping/template-families/901/variant-create-context",
        params={"file_id": 904},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["resolved_object_type"] == "variant_create"
    assert payload["data"]["family"]["id"] == 901
    assert payload["data"]["active_version"]["id"] == 902
    assert payload["data"]["existing_variants"][0]["variant_key"] == "monthly_slash"
    assert payload["data"]["current_file"]["id"] == 904


@pytest.mark.asyncio
async def test_save_mapping_template_accepts_async_session(
    template_update_context_client,
):
    client, session_factory = template_update_context_client

    response = await client.post(
        "/api/field-mapping/templates/save",
        json={
            "platform": "shopee",
            "data_domain": "orders",
            "granularity": "daily",
            "header_row": 1,
            "header_columns": ["order_id", "profit(RMB)", "buyer_payment(RMB)"],
            "deduplication_fields": ["order_id"],
            "template_name": "async_save_template_test",
            "created_by": "test",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    template_id = payload["data"]["template_id"]
    assert isinstance(template_id, int)

    async with session_factory() as session:
        result = await session.execute(
            text("SELECT template_name, header_columns FROM core.field_mapping_templates WHERE id = :id"),
            {"id": template_id},
        )
        row = result.mappings().one()
        assert row["template_name"] == "async_save_template_test"
        header_columns = row["header_columns"]
        if isinstance(header_columns, str):
            header_columns = json.loads(header_columns)
        assert header_columns == ["order_id", "profit(RMB)", "buyer_payment(RMB)"]


@pytest.mark.asyncio
async def test_save_mapping_template_rejects_date_targets_without_parse_rules(
    template_update_context_client,
):
    client, _ = template_update_context_client

    response = await client.post(
        "/api/field-mapping/templates/save",
        json={
            "platform": "shopee",
            "data_domain": "orders",
            "granularity": "daily",
            "header_row": 1,
            "header_columns": ["order_id", "order_time"],
            "deduplication_fields": ["order_id"],
            "template_name": "missing_metric_date_rules",
            "created_by": "test",
            "mappings": {
                "order_id": {"standard_field": "order_id", "confidence": 1.0},
                "order_time": {"standard_field": "metric_date", "confidence": 1.0},
            },
        },
    )

    assert response.status_code == 400
    assert "field_parse_rules" in response.text
    assert "metric_date" in response.text


@pytest.mark.asyncio
async def test_save_mapping_template_persists_field_parse_rules_and_update_context_returns_them(
    template_update_context_client,
):
    client, session_factory = template_update_context_client
    parse_rules = [
        {
            "target_field": "metric_date",
            "source_column": "order_time",
            "value_kind": "single_date",
            "date_format": "yyyy-mm-dd hh:mm:ss",
            "strict": True,
        }
    ]

    response = await client.post(
        "/api/field-mapping/templates/save",
        json={
            "platform": "shopee",
            "data_domain": "orders",
            "granularity": "daily",
            "header_row": 1,
            "header_columns": ["order_id", "order_time"],
            "deduplication_fields": ["order_id"],
            "template_name": "metric_date_rules_template",
            "created_by": "test",
            "mappings": {
                "order_id": {"standard_field": "order_id", "confidence": 1.0},
                "order_time": {"standard_field": "metric_date", "confidence": 1.0},
            },
            "field_parse_rules": parse_rules,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    template_id = payload["data"]["template_id"]

    async with session_factory() as session:
        result = await session.execute(
            text("SELECT field_parse_rules FROM core.field_mapping_templates WHERE id = :id"),
            {"id": template_id},
        )
        row = result.mappings().one()
        field_parse_rules = row["field_parse_rules"]
        if isinstance(field_parse_rules, str):
            field_parse_rules = json.loads(field_parse_rules)
        assert len(field_parse_rules) == 1
        assert field_parse_rules[0]["target_field"] == "metric_date"
        assert field_parse_rules[0]["source_column"] == "order_time"
        assert field_parse_rules[0]["value_kind"] == "single_date"
        assert field_parse_rules[0]["date_format"] == "yyyy-mm-dd hh:mm:ss"
        assert field_parse_rules[0]["strict"] is True
        assert field_parse_rules[0]["source_label"] == "order_time"
        assert "metric_date" in field_parse_rules[0]["source_aliases"]

    context_response = await client.get(
        f"/api/field-mapping/templates/{template_id}/update-context",
        params={"mode": "core-only"},
    )

    assert context_response.status_code == 200
    context_payload = context_response.json()
    assert context_payload["success"] is True
    returned_rules = context_payload["data"]["template"]["field_parse_rules"]
    assert len(returned_rules) == 1
    assert returned_rules[0]["target_field"] == "metric_date"
    assert returned_rules[0]["source_column"] == "order_time"
    assert returned_rules[0]["value_kind"] == "single_date"
    assert returned_rules[0]["date_format"] == "yyyy-mm-dd hh:mm:ss"
    assert returned_rules[0]["strict"] is True
    assert returned_rules[0]["source_label"] == "order_time"


@pytest.mark.asyncio
async def test_save_mapping_template_persists_header_bindings_and_update_context_returns_them(
    template_update_context_client,
):
    client, session_factory = template_update_context_client
    header_bindings = [
        {
            "raw_name": "Unnamed: 0",
            "display_name": "日期",
            "semantic_role": "metric_date",
            "aliases": ["日期", "统计日期"],
            "position": 0,
            "sample_type": "date",
            "confidence": 0.98,
        },
        {
            "raw_name": "GMV",
            "display_name": "GMV",
            "semantic_role": None,
            "aliases": [],
            "position": 1,
            "sample_type": "number",
            "confidence": 0.5,
        },
    ]

    response = await client.post(
        "/api/field-mapping/templates/save",
        json={
            "platform": "shopee",
            "data_domain": "analytics",
            "granularity": "daily",
            "header_row": 0,
            "header_columns": ["Unnamed: 0", "GMV"],
            "deduplication_fields": ["Unnamed: 0"],
            "template_name": "header_bindings_template",
            "created_by": "test",
            "header_bindings": header_bindings,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    template_id = payload["data"]["template_id"]

    async with session_factory() as session:
        result = await session.execute(
            text("SELECT header_bindings FROM core.field_mapping_templates WHERE id = :id"),
            {"id": template_id},
        )
        row = result.mappings().one()
        persisted_header_bindings = row["header_bindings"]
        if isinstance(persisted_header_bindings, str):
            persisted_header_bindings = json.loads(persisted_header_bindings)
        assert persisted_header_bindings[0]["raw_name"] == "Unnamed: 0"
        assert persisted_header_bindings[0]["semantic_key"] == "metric_date"
        assert persisted_header_bindings[0]["required"] is False
        assert persisted_header_bindings[0]["hash_participates"] is True
        assert persisted_header_bindings[1]["raw_name"] == "GMV"

    context_response = await client.get(
        f"/api/field-mapping/templates/{template_id}/update-context",
        params={"mode": "core-only"},
    )

    assert context_response.status_code == 200
    context_payload = context_response.json()
    assert context_payload["success"] is True
    returned_bindings = context_payload["data"]["template"]["header_bindings"]
    assert returned_bindings[0]["semantic_key"] == "metric_date"
    assert returned_bindings[0]["hash_participates"] is True
    assert context_payload["data"]["template"]["hash_participating_semantic_keys"] == ["metric_date"]


@pytest.mark.asyncio
async def test_save_mapping_template_accepts_file_date_token_parse_rules(
    template_update_context_client,
):
    client, session_factory = template_update_context_client
    parse_rules = [
        {
            "target_field": "metric_date",
            "source_column": "__file_date_from__",
            "value_kind": "single_date",
            "date_format": "yyyy-mm-dd",
            "strict": True,
        }
    ]

    response = await client.post(
        "/api/field-mapping/templates/save",
        json={
            "platform": "shopee",
            "data_domain": "analytics",
            "granularity": "daily",
            "header_row": 0,
            "header_columns": ["商品编号", "商品", "销售额（已下订单） (SGD)"],
            "deduplication_fields": ["metric_date"],
            "template_name": "analytics_file_date_rule",
            "created_by": "test",
            "mappings": {
                "商品": {"standard_field": "product_name", "confidence": 1.0},
            },
            "field_parse_rules": parse_rules,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    template_id = payload["data"]["template_id"]

    async with session_factory() as session:
        result = await session.execute(
            text("SELECT field_parse_rules FROM core.field_mapping_templates WHERE id = :id"),
            {"id": template_id},
        )
        row = result.mappings().one()
        field_parse_rules = row["field_parse_rules"]
        if isinstance(field_parse_rules, str):
            field_parse_rules = json.loads(field_parse_rules)
        assert len(field_parse_rules) == 1
        assert field_parse_rules[0]["target_field"] == "metric_date"
        assert field_parse_rules[0]["source_column"] == "__file_date_from__"
        assert field_parse_rules[0]["value_kind"] == "single_date"
        assert field_parse_rules[0]["date_format"] == "yyyy-mm-dd"
        assert field_parse_rules[0]["strict"] is True
        assert field_parse_rules[0]["source_aliases"] == []


@pytest.mark.asyncio
async def test_save_mapping_template_accepts_time_of_day_parse_rule_with_date_anchor(
    template_update_context_client,
):
    client, session_factory = template_update_context_client

    response = await client.post(
        "/api/field-mapping/templates/save",
        json={
            "platform": "shopee",
            "data_domain": "traffic",
            "granularity": "daily",
            "header_row": 0,
            "header_columns": ["小时", "浏览量"],
            "deduplication_fields": ["metric_date", "period_start_time"],
            "template_name": "traffic_hourly_time_of_day_rule",
            "created_by": "test",
            "header_bindings": [
                {
                    "raw_name": "小时",
                    "display_name": "小时",
                    "semantic_key": "period_start_time",
                    "semantic_review_status": "confirmed_semantic",
                },
                {
                    "raw_name": "浏览量",
                    "display_name": "浏览量",
                    "semantic_key": "page_views",
                    "semantic_review_status": "confirmed_semantic",
                },
            ],
            "field_parse_rules": [
                {
                    "target_field": "metric_date",
                    "source_column": "__file_date_from__",
                    "value_kind": "single_date",
                    "date_format": "yyyy-mm-dd",
                    "strict": True,
                },
                {
                    "target_field": "period_start_time",
                    "source_column": "小时",
                    "value_kind": "time_of_day",
                    "date_format": "hh:mm",
                    "date_anchor": "__file_date_from__",
                    "strict": True,
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    template_id = payload["data"]["template_id"]

    async with session_factory() as session:
        result = await session.execute(
            text("SELECT field_parse_rules FROM core.field_mapping_templates WHERE id = :id"),
            {"id": template_id},
        )
        row = result.mappings().one()
        field_parse_rules = row["field_parse_rules"]
        if isinstance(field_parse_rules, str):
            field_parse_rules = json.loads(field_parse_rules)
        hour_rule = next(rule for rule in field_parse_rules if rule["target_field"] == "period_start_time")
        assert hour_rule["value_kind"] == "time_of_day"
        assert hour_rule["date_anchor"] == "__file_date_from__"


@pytest.mark.asyncio
async def test_save_mapping_template_preserves_raw_non_orders_headers(
    template_update_context_client,
):
    client, session_factory = template_update_context_client

    response = await client.post(
        "/api/field-mapping/templates/save",
        json={
            "platform": "shopee",
            "data_domain": "analytics",
            "granularity": "monthly",
            "header_row": 1,
            "header_columns": ["platform_sku", "period_start_date", "Current Item Status", "销售额（已下订单） (COP)"],
            "deduplication_fields": ["period_start_date"],
            "template_name": "raw_header_preserve_test",
            "created_by": "test",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    template_id = payload["data"]["template_id"]

    async with session_factory() as session:
        result = await session.execute(
            text("SELECT header_columns FROM core.field_mapping_templates WHERE id = :id"),
            {"id": template_id},
        )
        row = result.mappings().one()
        header_columns = row["header_columns"]
        if isinstance(header_columns, str):
            header_columns = json.loads(header_columns)
        assert header_columns == ["platform_sku", "period_start_date", "Current Item Status", "销售额（已下订单） (COP)"]


@pytest.mark.asyncio
async def test_template_update_context_orders_ignores_currency_suffix_difference(
    template_update_context_client,
    monkeypatch,
):
    client, session_factory = template_update_context_client

    async with session_factory() as session:
        template = FieldMappingTemplate(
            platform="miaoshou",
            data_domain="orders",
            granularity="daily",
            sub_domain=None,
            header_row=1,
            header_columns=["订单编号", "利润", "买家支付"],
            deduplication_fields=["订单编号"],
            template_name="miaoshou_orders_daily_profit_legacy",
            version=1,
            status="published",
            field_count=3,
            created_by="test",
        )
        file_record = CatalogFile(
            file_path="data/raw/miaoshou/orders/orders_daily_rmb_demo.xlsx",
            file_name="orders_daily_rmb_demo.xlsx",
            source="data/raw",
            platform_code="miaoshou",
            source_platform="miaoshou",
            data_domain="orders",
            granularity="daily",
            status="pending",
            first_seen_at=datetime.now(timezone.utc),
        )
        session.add(template)
        session.add(file_record)
        await session.commit()
        await session.refresh(template)
        await session.refresh(file_record)

    from backend.routers import field_mapping_templates as router_module

    async def fake_load_file_update_summary(*_, **__):
        return {
            "file": {
                "id": file_record.id,
                "file_name": file_record.file_name,
                "platform": "miaoshou",
                "domain": "orders",
                "granularity": "daily",
                "sub_domain": None,
            },
            "header_columns": ["订单编号", "利润(RMB)", "买家支付(RMB)"],
            "header_bindings": [],
        }

    monkeypatch.setattr(
        router_module,
        "_load_file_update_summary",
        fake_load_file_update_summary,
        raising=False,
    )

    response = await client.get(
        f"/api/field-mapping/templates/{template.id}/update-context",
        params={"mode": "with-sample", "file_id": file_record.id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True

    data = payload["data"]
    assert data["added_fields"] == []
    assert data["removed_fields"] == []
    assert data["header_changes"]["detected"] is False
    assert data["header_changes"]["is_exact_match"] is True
@pytest.mark.asyncio
async def test_detect_header_changes_endpoint_returns_resolved_payload(
    template_update_context_client,
):
    client, session_factory = template_update_context_client

    async with session_factory() as session:
        template = FieldMappingTemplate(
            platform="shopee",
            data_domain="orders",
            granularity="daily",
            sub_domain=None,
            header_row=1,
            header_columns=["order_id", "platform_sku", "amount"],
            deduplication_fields=["order_id"],
            template_name="shopee_orders_daily_detect_v1",
            version=1,
            status="published",
            field_count=3,
            created_by="test",
        )
        session.add(template)
        await session.commit()
        await session.refresh(template)

    response = await client.post(
        "/api/field-mapping/templates/detect-header-changes",
        json={
            "template_id": template.id,
            "current_columns": ["order_id", "amount", "new_metric"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["header_changes"]["detected"] is True
    assert "new_metric" in payload["header_changes"]["added_fields"]


@pytest.mark.asyncio
async def test_save_mapping_template_returns_versioning_metadata(
    template_update_context_client,
):
    client, session_factory = template_update_context_client

    first_response = await client.post(
        "/api/field-mapping/templates/save",
        json={
            "platform": "shopee",
            "data_domain": "orders",
            "granularity": "daily",
            "header_row": 1,
            "header_columns": ["order_id", "amount"],
            "deduplication_fields": ["order_id"],
            "created_by": "test",
        },
    )
    assert first_response.status_code == 200
    first_payload = first_response.json()
    assert first_payload["success"] is True
    assert first_payload["data"]["version"] == 1
    assert first_payload["data"]["operation"] == "created"
    assert first_payload["data"]["archived_template_id"] is None

    second_response = await client.post(
        "/api/field-mapping/templates/save",
        json={
            "platform": "shopee",
            "data_domain": "orders",
            "granularity": "daily",
            "header_row": 1,
            "header_columns": ["order_id", "amount", "new_metric"],
            "deduplication_fields": ["order_id"],
            "created_by": "test",
            "save_mode": "new_version",
        },
    )

    assert second_response.status_code == 200
    second_payload = second_response.json()
    assert second_payload["success"] is True
    assert second_payload["data"]["version"] == 2
    assert second_payload["data"]["operation"] == "new_version"
    assert second_payload["data"]["archived_template_id"] == first_payload["data"]["template_id"]
    assert second_payload["data"]["template_name"].endswith("_v2")


@pytest.mark.asyncio
async def test_save_mapping_template_rejects_family_hash_key_downgrade(
    template_update_context_client,
):
    client, _session_factory = template_update_context_client

    first_response = await client.post(
        "/api/field-mapping/templates/save",
        json={
            "platform": "shopee",
            "data_domain": "orders",
            "granularity": "daily",
            "header_row": 0,
            "header_columns": ["订单号", "SKU", "金额"],
            "deduplication_fields": ["订单号", "SKU"],
            "mappings": {
                "订单号": {"standard_field": "order_id", "confidence": 1.0},
                "SKU": {"standard_field": "sku_id", "confidence": 1.0},
            },
            "created_by": "test",
        },
    )
    assert first_response.status_code == 200

    second_response = await client.post(
        "/api/field-mapping/templates/save",
        json={
            "platform": "shopee",
            "data_domain": "orders",
            "granularity": "daily",
            "header_row": 0,
            "header_columns": ["订单编号", "金额"],
            "deduplication_fields": ["订单编号"],
            "mappings": {
                "订单编号": {"standard_field": "order_id", "confidence": 1.0},
            },
            "created_by": "test",
            "save_mode": "new_version",
        },
    )

    assert second_response.status_code == 400
    payload = second_response.json()
    assert "缺少必要 hash 语义字段: sku_id" in payload["message"]
    assert "同一模板家族必须保持同一套 data_hash 语义字段" in payload["message"]


@pytest.mark.asyncio
async def test_save_mapping_template_allows_source_header_rename_when_semantic_hash_keys_match(
    template_update_context_client,
):
    client, session_factory = template_update_context_client

    async with session_factory() as session:
        legacy_template = FieldMappingTemplate(
            platform="tiktok",
            data_domain="products",
            granularity="monthly",
            sub_domain=None,
            header_row=0,
            header_columns=["ID", "Status"],
            deduplication_fields=["ID", "Status"],
            header_bindings=[
                {
                    "raw_name": "ID",
                    "semantic_key": "product_id",
                    "semantic_review_status": "confirmed_semantic",
                },
                {
                    "raw_name": "Status",
                    "semantic_key": "item_status",
                    "semantic_review_status": "confirmed_semantic",
                },
            ],
            template_name="tiktok_products_monthly_legacy_source_names",
            version=1,
            status="published",
            field_count=2,
            created_by="test",
        )
        session.add(legacy_template)
        await session.commit()

    response = await client.post(
        "/api/field-mapping/templates/save",
        json={
            "platform": "tiktok",
            "data_domain": "products",
            "granularity": "monthly",
            "header_row": 0,
            "header_columns": ["Product ID", "Item Status"],
            "deduplication_fields": ["Product ID", "Item Status"],
            "created_by": "test",
            "save_mode": "new_version",
            "header_bindings": [
                {
                    "raw_name": "Product ID",
                    "semantic_key": "product_id",
                    "semantic_review_status": "confirmed_semantic",
                },
                {
                    "raw_name": "Item Status",
                    "semantic_key": "item_status",
                    "semantic_review_status": "confirmed_semantic",
                },
            ],
            "field_parse_rules": [
                {
                    "target_field": "period_start_date",
                    "source_column": "__file_date_from__",
                    "value_kind": "single_date",
                    "date_format": "yyyy-mm-dd",
                },
                {
                    "target_field": "period_end_date",
                    "source_column": "__file_date_to__",
                    "value_kind": "single_date",
                    "date_format": "yyyy-mm-dd",
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    template_id = payload["data"]["template_id"]

    async with session_factory() as session:
        template = await session.get(FieldMappingTemplate, template_id)

    assert template.deduplication_fields == ["product_id", "item_status"]


@pytest.mark.asyncio
async def test_save_mapping_template_returns_structured_family_hash_change_for_semantic_change(
    template_update_context_client,
):
    client, session_factory = template_update_context_client

    async with session_factory() as session:
        legacy_template = FieldMappingTemplate(
            platform="tiktok",
            data_domain="products",
            granularity="monthly",
            sub_domain=None,
            header_row=0,
            header_columns=["Product Name"],
            deduplication_fields=["Product Name"],
            header_bindings=[
                {
                    "raw_name": "Product Name",
                    "semantic_key": "product_name",
                    "semantic_review_status": "confirmed_semantic",
                }
            ],
            template_name="tiktok_products_monthly_legacy_product_name_hash",
            version=1,
            status="published",
            field_count=1,
            created_by="test",
        )
        session.add(legacy_template)
        await session.commit()

    response = await client.post(
        "/api/field-mapping/templates/save",
        json={
            "platform": "tiktok",
            "data_domain": "products",
            "granularity": "monthly",
            "header_row": 0,
            "header_columns": ["Product ID"],
            "deduplication_fields": ["Product ID"],
            "created_by": "test",
            "save_mode": "new_version",
            "header_bindings": [
                {
                    "raw_name": "Product ID",
                    "semantic_key": "product_id",
                    "semantic_review_status": "confirmed_semantic",
                }
            ],
            "field_parse_rules": [
                {
                    "target_field": "period_start_date",
                    "source_column": "__file_date_from__",
                    "value_kind": "single_date",
                    "date_format": "yyyy-mm-dd",
                },
                {
                    "target_field": "period_end_date",
                    "source_column": "__file_date_to__",
                    "value_kind": "single_date",
                    "date_format": "yyyy-mm-dd",
                },
            ],
        },
    )

    assert response.status_code == 400
    payload = response.json()
    hash_policy = payload["data"]["hash_policy"]
    assert hash_policy["family_hash_keys"] == ["product_name"]
    assert hash_policy["current_hash_keys"] == ["product_id"]
    assert hash_policy["semantic_hash_key_changes"] == [
        {"change": "missing", "semantic_key": "product_name"},
        {"change": "added", "semantic_key": "product_id"},
    ]
    assert hash_policy["suggested_action"] == "migrate_family_hash_keys"
    assert "Hash" in payload["message"]


@pytest.mark.asyncio
async def test_save_mapping_template_syncs_hash_participation_from_selected_semantic_keys(
    template_update_context_client,
):
    client, session_factory = template_update_context_client

    response = await client.post(
        "/api/field-mapping/templates/save",
        json={
            "platform": "shopee",
            "data_domain": "orders",
            "granularity": "daily",
            "header_row": 0,
            "header_columns": ["订单号", "日期", "金额"],
            "deduplication_fields": ["订单号"],
            "header_bindings": [
                {
                    "raw_name": "订单号",
                    "display_name": "订单号",
                    "semantic_key": "order_id",
                    "semantic_review_status": "confirmed_semantic",
                    "hash_participates": False,
                },
                {
                    "raw_name": "日期",
                    "display_name": "日期",
                    "semantic_key": "metric_date",
                    "semantic_review_status": "confirmed_semantic",
                    "hash_participates": True,
                },
            ],
            "created_by": "test",
        },
    )

    assert response.status_code == 200
    template_id = response.json()["data"]["template_id"]
    async with session_factory() as session:
        template = await session.get(FieldMappingTemplate, template_id)

    assert template.deduplication_fields == ["order_id"]
    bindings_by_key = {binding["semantic_key"]: binding for binding in template.header_bindings}
    assert bindings_by_key["order_id"]["hash_participates"] is True
    assert bindings_by_key["metric_date"]["hash_participates"] is False


@pytest.mark.asyncio
async def test_save_mapping_template_rejects_confirmed_non_semantic_dedup_field(
    template_update_context_client,
):
    client, _session_factory = template_update_context_client

    response = await client.post(
        "/api/field-mapping/templates/save",
        json={
            "platform": "tiktok",
            "data_domain": "products",
            "granularity": "daily",
            "header_row": 0,
            "header_columns": ["商品名", "商品 ID"],
            "deduplication_fields": ["商品名"],
            "header_bindings": [
                {
                    "raw_name": "商品名",
                    "display_name": "商品名",
                    "semantic_key": None,
                    "semantic_review_status": "confirmed_non_semantic",
                    "hash_participates": False,
                },
                {
                    "raw_name": "商品 ID",
                    "display_name": "商品 ID",
                    "semantic_key": "product_id",
                    "semantic_review_status": "confirmed_semantic",
                    "hash_participates": True,
                },
            ],
            "created_by": "test",
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert "商品名" in payload["message"]


@pytest.mark.asyncio
async def test_list_templates_returns_wrapped_template_collection(
    template_update_context_client,
):
    client, session_factory = template_update_context_client

    async with session_factory() as session:
        session.add(
            FieldMappingTemplate(
                platform="shopee",
                data_domain="orders",
                granularity="daily",
                sub_domain=None,
                header_row=1,
                header_columns=["order_id", "amount"],
                deduplication_fields=["order_id"],
                template_name="shopee_orders_daily_v1",
                version=1,
                status="published",
                field_count=2,
                created_by="test",
            )
        )
        await session.commit()

    response = await client.get("/api/field-mapping/templates/list")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["count"] == 1
    assert payload["data"]["templates"][0]["template_name"] == "shopee_orders_daily_v1"


@pytest.mark.asyncio
async def test_hash_policy_preview_returns_structured_missing_period_group(
    template_update_context_client,
):
    client, _session_factory = template_update_context_client

    response = await client.post(
        "/api/field-mapping/templates/hash-policy-preview",
        json={
            "data_domain": "products",
            "granularity": "monthly",
            "sub_domain": None,
            "deduplication_fields": ["product_id"],
            "header_bindings": [
                {
                    "raw_name": "Product ID",
                    "semantic_key": "product_id",
                    "semantic_review_status": "confirmed_semantic",
                }
            ],
            "field_parse_rules": [],
            "sample_rows": [],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["passed"] is False
    assert data["missing_required_groups"][0]["key"] == "products_period_date"
    assert data["effective_components"]["system_scope_fields"] == [
        "platform_code",
        "shop_id",
        "data_domain",
        "granularity",
        "sub_domain",
    ]


@pytest.mark.asyncio
async def test_hash_policy_preview_accepts_selected_derived_metric_date(
    template_update_context_client,
):
    client, _session_factory = template_update_context_client

    response = await client.post(
        "/api/field-mapping/templates/hash-policy-preview",
        json={
            "data_domain": "products",
            "granularity": "monthly",
            "deduplication_fields": ["product_id", "metric_date"],
            "header_bindings": [
                {
                    "raw_name": "Product ID",
                    "semantic_key": "product_id",
                    "semantic_review_status": "confirmed_semantic",
                }
            ],
            "field_parse_rules": [
                {
                    "target_field": "metric_date",
                    "source_column": "__file_date_from__",
                    "value_kind": "single_date",
                    "date_format": "yyyy-mm-dd",
                }
            ],
            "sample_rows": [],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["passed"] is True
    assert data["can_save"] is True
    assert data["normalized_deduplication_fields"] == ["product_id", "metric_date"]
    assert data["blocking_errors"] == []
    assert data["normalized_header_bindings"][0]["semantic_key"] == "product_id"
    assert data["effective_components"]["derived_identity_fields"] == ["metric_date"]
    by_key = {option["semantic_key"]: option for option in data["hash_options"]}
    assert by_key["product_id"]["eligible"] is True
    assert by_key["product_id"]["recommended"] is True


@pytest.mark.asyncio
async def test_hash_policy_preview_returns_dynamic_hash_options_for_edited_bindings(
    template_update_context_client,
):
    client, _session_factory = template_update_context_client

    response = await client.post(
        "/api/field-mapping/templates/hash-policy-preview",
        json={
            "data_domain": "products",
            "granularity": "monthly",
            "deduplication_fields": ["item_status"],
            "header_bindings": [
                {
                    "raw_name": "商品 ID",
                    "semantic_key": "product_id",
                    "semantic_review_status": "confirmed_semantic",
                },
                {
                    "raw_name": "发品状态",
                    "semantic_key": "item_status",
                    "semantic_review_status": "confirmed_semantic",
                },
                {
                    "raw_name": "GMV",
                    "semantic_key": "gmv",
                    "semantic_review_status": "confirmed_semantic",
                },
            ],
            "field_parse_rules": [
                {
                    "target_field": "metric_date",
                    "source_column": "__file_date_from__",
                    "value_kind": "single_date",
                    "date_format": "yyyy-mm-dd",
                }
            ],
            "sample_rows": [],
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["can_save"] is False
    assert data["missing_required_groups"][0]["key"] == "products_identity"
    by_key = {option["semantic_key"]: option for option in data["hash_options"]}
    assert by_key["product_id"]["eligible"] is True
    assert by_key["product_id"]["recommended"] is True
    assert by_key["item_status"]["eligible"] is True
    assert by_key["item_status"]["weak_identity"] is True
    assert by_key["item_status"]["legacy_compatible"] is True
    assert by_key["gmv"]["eligible"] is False
    assert by_key["gmv"]["blocked_reason"]


@pytest.mark.asyncio
async def test_save_mapping_template_returns_structured_hash_policy_on_failure(
    template_update_context_client,
):
    client, _session_factory = template_update_context_client

    response = await client.post(
        "/api/field-mapping/templates/save",
        json={
            "platform": "shopee",
            "data_domain": "products",
            "granularity": "monthly",
            "header_row": 0,
            "header_columns": ["Product ID", "Product Name"],
            "deduplication_fields": ["product_id"],
            "template_name": "products_missing_period_hash_policy",
            "created_by": "test",
            "header_bindings": [
                {
                    "raw_name": "Product ID",
                    "semantic_key": "product_id",
                    "semantic_review_status": "confirmed_semantic",
                },
                {
                    "raw_name": "Product Name",
                    "semantic_key": "product_name",
                    "semantic_review_status": "confirmed_semantic",
                },
            ],
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert payload["data"]["hash_policy"]["passed"] is False
    assert payload["data"]["hash_policy"]["requirement_groups"]
    assert payload["data"]["hash_policy"]["missing_required_groups"][0]["key"] == "products_period_date"
    assert payload["data"]["hash_policy"]["can_save"] is False
    assert payload["data"]["hash_policy"]["blocking_errors"]


@pytest.mark.asyncio
async def test_hash_policy_preview_rejects_unresolved_deduplication_field_with_save_readiness_shape(
    template_update_context_client,
):
    client, _session_factory = template_update_context_client

    response = await client.post(
        "/api/field-mapping/templates/hash-policy-preview",
        json={
            "data_domain": "products",
            "granularity": "monthly",
            "deduplication_fields": ["product_id", "metric_date"],
            "header_bindings": [
                {
                    "raw_name": "Product Name",
                    "semantic_key": "product_name",
                    "semantic_review_status": "confirmed_semantic",
                }
            ],
            "field_parse_rules": [
                {
                    "target_field": "metric_date",
                    "source_column": "__file_date_from__",
                    "value_kind": "single_date",
                    "date_format": "yyyy-mm-dd",
                }
            ],
            "sample_rows": [],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["passed"] is False
    assert data["can_save"] is False
    assert data["unresolved_deduplication_fields"] == ["product_id"]
    assert "product_id" in data["blocking_errors"][0]


@pytest.mark.asyncio
async def test_hash_policy_preview_and_save_share_same_binding_resolution_for_save_readiness(
    template_update_context_client,
):
    client, _session_factory = template_update_context_client

    request_payload = {
        "platform": "shopee",
        "data_domain": "products",
        "granularity": "monthly",
        "header_row": 0,
        "header_columns": ["Product Name"],
        "deduplication_fields": ["product_id", "metric_date"],
        "created_by": "test",
        "header_bindings": [
            {
                "raw_name": "Product Name",
                "semantic_key": "product_name",
                "semantic_review_status": "confirmed_semantic",
            }
        ],
        "field_parse_rules": [
            {
                "target_field": "metric_date",
                "source_column": "__file_date_from__",
                "value_kind": "single_date",
                "date_format": "yyyy-mm-dd",
            }
        ],
    }

    preview_response = await client.post(
        "/api/field-mapping/templates/hash-policy-preview",
        json={
            "data_domain": request_payload["data_domain"],
            "granularity": request_payload["granularity"],
            "deduplication_fields": request_payload["deduplication_fields"],
            "header_bindings": request_payload["header_bindings"],
            "field_parse_rules": request_payload["field_parse_rules"],
            "sample_rows": [],
        },
    )
    assert preview_response.status_code == 200
    preview_data = preview_response.json()["data"]
    assert preview_data["can_save"] is False

    save_response = await client.post("/api/field-mapping/templates/save", json=request_payload)
    assert save_response.status_code == 400
    save_payload = save_response.json()
    assert save_payload["data"]["hash_policy"]["can_save"] is False
    assert save_payload["data"]["hash_policy"]["blocking_errors"] == preview_data["blocking_errors"]
    assert (
        save_payload["data"]["hash_policy"]["unresolved_deduplication_fields"]
        == preview_data["unresolved_deduplication_fields"]
    )


@pytest.mark.asyncio
async def test_save_mapping_template_normalizes_raw_deduplication_fields_to_canonical_keys(
    template_update_context_client,
):
    client, session_factory = template_update_context_client

    response = await client.post(
        "/api/field-mapping/templates/save",
        json={
            "platform": "shopee",
            "data_domain": "products",
            "granularity": "monthly",
            "header_row": 0,
            "header_columns": ["Product ID"],
            "deduplication_fields": ["Product ID", "metric_date"],
            "template_name": "products_monthly_raw_dedup_fields",
            "created_by": "test",
            "header_bindings": [
                {
                    "raw_name": "Product ID",
                    "semantic_key": "product_id",
                    "semantic_review_status": "confirmed_semantic",
                }
            ],
            "field_parse_rules": [
                {
                    "target_field": "metric_date",
                    "source_column": "__file_date_from__",
                    "value_kind": "single_date",
                    "date_format": "yyyy-mm-dd",
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    template_id = payload["data"]["template_id"]

    async with session_factory() as session:
        template = await session.get(FieldMappingTemplate, template_id)

    assert template.deduplication_fields == ["product_id", "metric_date"]


@pytest.mark.asyncio
async def test_default_deduplication_fields_endpoint_returns_wrapped_payload(
    template_update_context_client,
):
    client, _ = template_update_context_client

    response = await client.get(
        "/api/field-mapping/templates/default-deduplication-fields",
        params={"data_domain": "orders"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["fields"]
    assert payload["data"]["description"]
    assert payload["data"]["reason"]


@pytest.mark.asyncio
async def test_apply_template_endpoint_returns_typed_payload(
    template_update_context_client,
):
    client, session_factory = template_update_context_client

    async with session_factory() as session:
        template = FieldMappingTemplate(
            platform="shopee",
            data_domain="orders",
            granularity="daily",
            sub_domain=None,
            header_row=1,
            header_columns=["order_id", "amount"],
            deduplication_fields=["order_id"],
            template_name="shopee_orders_daily_v1",
            version=1,
            status="published",
            field_count=2,
            created_by="test",
        )
        session.add(template)
        await session.commit()
        await session.refresh(template)

    response = await client.post(
        "/api/field-mapping/templates/apply",
        json={
            "template_id": template.id,
            "columns": ["order_id", "amount", "new_metric"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["matched"] == 2
    assert payload["unmatched"] == 1
    assert payload["unmatched_columns"] == ["new_metric"]
    assert payload["config"]["header_row"] == 1
    assert payload["template_name"] == "shopee_orders_daily_v1"
    assert payload["template_version"] == 1
