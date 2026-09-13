from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import inspect

from backend.schemas.product_center import (
    SkuOperatingProfileCreateRequest,
    SkuOperatingProfileUpdateRequest,
)
from modules.core.db import SkuOperatingProfile, SkuProfitEstimate


def test_operating_profile_has_site_and_warehouse_grain():
    columns = {column.name for column in inspect(SkuOperatingProfile).columns}
    assert {
        "profile_id",
        "sku_id",
        "platform_code",
        "shop_id",
        "site_code",
        "warehouse_code",
        "selling_price",
        "platform_fee_rate",
        "expected_logistics_cost",
        "expected_storage_cost",
        "effective_from",
        "effective_to",
    } <= columns
    assert any(
        constraint.name == "uq_sku_operating_profile_current"
        for constraint in SkuOperatingProfile.__table__.constraints
    ) or any(index.name == "uq_sku_operating_profile_current" for index in SkuOperatingProfile.__table__.indexes)


def test_profit_estimate_preserves_legacy_and_site_columns():
    columns = {column.name for column in inspect(SkuProfitEstimate).columns}
    assert {
        "sku_id",
        "operating_profile_id",
        "platform_code",
        "shop_id",
        "site_code",
        "warehouse_code",
        "estimated_contribution_profit",
    } <= columns


def test_operating_profile_requires_complete_business_key():
    request = SkuOperatingProfileCreateRequest(
        sku_id=1,
        platform_code="tiktok",
        shop_id="shop-1",
        site_code="PH",
        warehouse_code="WH-1",
        selling_price=Decimal("100"),
    )
    assert request.site_code == "PH"
    with pytest.raises(ValueError):
        SkuOperatingProfileCreateRequest(
            sku_id=1,
            platform_code="tiktok",
            shop_id="shop-1",
            site_code="",
            warehouse_code="WH-1",
        )


def test_operating_profile_update_allows_cost_and_selling_fields_only():
    request = SkuOperatingProfileUpdateRequest(
        selling_price=120,
        default_coupon_amount=5,
        expected_logistics_cost=10,
        expected_storage_cost=2,
        platform_fee_rate=0.1,
    )
    assert request.model_dump(exclude_unset=True) == {
        "selling_price": 120,
        "default_coupon_amount": 5,
        "expected_logistics_cost": 10,
        "expected_storage_cost": 2,
        "platform_fee_rate": 0.1,
    }


def test_operating_profile_response_contract_includes_sku_identity_and_latest_profit_summary():
    source = Path("backend/schemas/product_center.py").read_text(encoding="utf-8")

    assert "sku_key: Optional[str]" in source
    assert "estimated_contribution_profit: Optional[float]" in source
    assert "estimated_margin_rate: Optional[float]" in source


def test_operating_profit_queries_confirmed_logistics_by_destination_and_warehouse():
    source = Path("backend/services/product_finance_service.py").read_text(encoding="utf-8")

    assert "warehouse_code: str | None" in source
    assert "GRNHeader.warehouse == warehouse_code" in source
    assert '"warehouse_code": profile.warehouse_code' in source


def test_site_sku_projection_has_a_separate_table_and_idempotent_business_key():
    service_source = Path("backend/services/feishu_projection_service.py").read_text(encoding="utf-8")
    schema_source = Path("modules/core/db/schema_parts/collection.py").read_text(encoding="utf-8")

    assert "site_sku_table_id" in schema_source
    assert "ERP-站点SKU经营" in service_source
    assert "platform_code + shop_id + site_code + warehouse_code + sku_id" in service_source


def test_feishu_projection_keeps_legacy_spu_sku_delivery_when_site_table_is_not_initialized():
    source = Path("backend/services/feishu_projection_service.py").read_text(encoding="utf-8")

    assert "not config.spu_table_id or not config.sku_table_id" in source
    assert "site_sku_table_id is not configured" in source


def test_site_projection_enqueue_is_limited_to_site_sku_mutations():
    source = Path("backend/domains/business/routers/product_center.py").read_text(encoding="utf-8")
    category_block = source[source.index("async def create_product_category"):source.index("async def update_product_category")]
    bill_block = source[source.index("async def create_logistics_bill"):source.index("async def create_logistics_batch")]

    assert "_enqueue_site_sku_projection" not in category_block
    assert "_enqueue_site_sku_projection" not in bill_block
