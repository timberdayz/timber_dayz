from datetime import datetime, timezone
import json

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


@pytest_asyncio.fixture
async def template_update_context_client():
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
async def test_template_update_context_returns_diff_and_deduplication_groups(
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

    async def fake_load_file_update_preview(db, file_id, header_row):
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
            "sample_data": {
                "order_id": "SO-1",
                "amount": "99.5",
                "platform_sku": "SKU-1",
                "new_metric": "7",
            },
            "preview_data": [
                {
                    "order_id": "SO-1",
                    "amount": "99.5",
                    "platform_sku": "SKU-1",
                    "new_metric": "7",
                },
                {
                    "order_id": "SO-2",
                    "amount": "120.0",
                    "platform_sku": "SKU-2",
                    "new_metric": "9",
                },
            ],
        }

    monkeypatch.setattr(
        router_module,
        "_load_file_update_preview",
        fake_load_file_update_preview,
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
    assert data["preview_data"][0]["order_id"] == "SO-1"
    assert data["header_changes"]["detected"] is True
    assert data["added_fields"] == ["new_metric"]
    assert data["removed_fields"] == ["shop_id"]
    assert data["existing_deduplication_fields_available"] == ["order_id"]
    assert data["existing_deduplication_fields_missing"] == ["shop_id"]
    assert data["recommended_deduplication_fields"] == ["order_id"]
    assert data["update_mode"] == "with-sample"


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
    assert data["recommended_deduplication_fields"] == ["order_id", "shop_id"]


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
        assert field_parse_rules[0]["source_aliases"] == []

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
        assert persisted_header_bindings == header_bindings

    context_response = await client.get(
        f"/api/field-mapping/templates/{template_id}/update-context",
        params={"mode": "core-only"},
    )

    assert context_response.status_code == 200
    context_payload = context_response.json()
    assert context_payload["success"] is True
    returned_bindings = context_payload["data"]["template"]["header_bindings"]
    assert returned_bindings == header_bindings


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
            "data_domain": "products",
            "granularity": "monthly",
            "header_row": 0,
            "header_columns": ["商品编号", "商品", "销售额（已下订单） (SGD)"],
            "deduplication_fields": ["商品编号"],
            "template_name": "products_file_date_rule",
            "created_by": "test",
            "mappings": {
                "商品编号": {"standard_field": "platform_sku", "confidence": 1.0},
                "商品": {"standard_field": "product_name", "confidence": 1.0},
                "sales": {"standard_field": "metric_date", "confidence": 1.0},
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
async def test_save_mapping_template_preserves_raw_non_orders_headers(
    template_update_context_client,
):
    client, session_factory = template_update_context_client

    response = await client.post(
        "/api/field-mapping/templates/save",
        json={
            "platform": "shopee",
            "data_domain": "products",
            "granularity": "monthly",
            "header_row": 1,
            "header_columns": ["Current Item Status", "销售额（已下订单） (COP)"],
            "deduplication_fields": ["Current Item Status"],
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
        assert header_columns == ["Current Item Status", "销售额（已下订单） (COP)"]


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

    async def fake_load_file_update_preview(*_, **__):
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
            "sample_data": {
                "订单编号": "MS-1",
                "利润(RMB)": "100",
                "买家支付(RMB)": "200",
            },
            "preview_data": [
                {
                    "订单编号": "MS-1",
                    "利润(RMB)": "100",
                    "买家支付(RMB)": "200",
                }
            ],
        }

    monkeypatch.setattr(
        router_module,
        "_load_file_update_preview",
        fake_load_file_update_preview,
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
