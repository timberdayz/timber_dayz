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

    from backend.routers import field_mapping_dictionary as router_module

    async def fake_load_file_update_preview(*_, **__):
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

    response = await client.get(
        f"/api/field-mapping/templates/{template.id}/update-context",
        params={"file_id": file_record.id},
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
    assert data["header_source"] == "template"
    assert data["existing_deduplication_fields_available"] == ["order_id"]
    assert data["existing_deduplication_fields_missing"] == ["missing_field"]
    assert data["recommended_deduplication_fields"] == ["order_id", "shop_id"]
