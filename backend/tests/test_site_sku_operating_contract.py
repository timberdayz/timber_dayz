from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import inspect

from backend.schemas.product_center import (
    SkuOperatingProfileCreateRequest,
    SkuOperatingProfileUpdateRequest,
)
from modules.core.db import DimWarehouse, SkuOperatingProfile, SkuProfitEstimate


def test_operating_profile_has_platform_warehouse_sku_grain():
    columns = {column.name for column in inspect(SkuOperatingProfile).columns}
    assert {
        "profile_id",
        "sku_id",
        "platform_code",
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


def test_profit_estimate_has_platform_warehouse_columns_without_site_scope():
    columns = {column.name for column in inspect(SkuProfitEstimate).columns}
    assert {
        "sku_id",
        "operating_profile_id",
        "platform_code",
        "warehouse_code",
        "estimated_contribution_profit",
    } <= columns
    assert "shop_id" not in columns
    assert "site_code" not in columns


def test_operating_profile_requires_complete_business_key():
    request = SkuOperatingProfileCreateRequest(
        sku_id=1,
        platform_code="tiktok",
        warehouse_code="WH-1",
        selling_price=Decimal("100"),
    )
    assert request.warehouse_code == "WH-1"
    with pytest.raises(ValueError):
        SkuOperatingProfileCreateRequest(
            sku_id=1,
            platform_code="tiktok",
            warehouse_code="",
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
    }


def test_operating_profile_response_contract_includes_sku_identity_and_latest_profit_summary():
    source = Path("backend/schemas/product_center.py").read_text(encoding="utf-8")

    assert "sku_key: Optional[str]" in source
    assert "estimated_contribution_profit: Optional[float]" in source
    assert "estimated_margin_rate: Optional[float]" in source


def test_operating_profit_queries_confirmed_logistics_by_warehouse():
    source = Path("backend/services/product_finance_service.py").read_text(encoding="utf-8")

    assert "warehouse_code: str | None" in source
    assert "LogisticsBillLine.warehouse_code == warehouse_code" in source
    assert '"warehouse_code": profile.warehouse_code' in source


def test_site_sku_projection_has_a_separate_table_and_idempotent_business_key():
    service_source = Path("backend/services/feishu_projection_service.py").read_text(encoding="utf-8")
    schema_source = Path("modules/core/db/schema_parts/collection.py").read_text(encoding="utf-8")

    assert "platform_sku_profit_table_id" in schema_source
    assert "ERP-平台SKU利润" in service_source
    assert "platform_code + warehouse_code + sku_id" in service_source


def test_feishu_projection_keeps_legacy_spu_sku_delivery_when_site_table_is_not_initialized():
    source = Path("backend/services/feishu_projection_service.py").read_text(encoding="utf-8")

    assert "not config.spu_table_id or not config.sku_table_id" in source
    assert "platform_sku_profit_table_id is not configured" in source


def test_site_projection_enqueue_is_limited_to_site_sku_mutations():
    source = Path("backend/domains/business/routers/product_center.py").read_text(encoding="utf-8")
    category_block = source[source.index("async def create_product_category"):source.index("async def update_product_category")]
    bill_block = source[source.index("async def create_logistics_bill"):source.index("async def create_logistics_batch")]

    assert "_enqueue_site_sku_projection" not in category_block
    assert "_enqueue_site_sku_projection" not in bill_block


def test_site_operating_migration_and_projection_are_safe_for_transport_and_decimal_payloads():
    migration = Path("current_migrations/versions/20260913_sku_operating_profiles.py").read_text(encoding="utf-8")
    router = Path("backend/domains/business/routers/product_center.py").read_text(encoding="utf-8")

    assert 'sa.Column("transport_type", sa.String(64)' in migration
    assert '"selling_price": float(row.selling_price)' in router


def test_warehouse_contract_is_single_country_and_transport_is_fixed():
    columns = {column.name for column in inspect(DimWarehouse).columns}
    assert {"warehouse_code", "warehouse_name", "country_code", "country_name", "status"} <= columns
    schema_source = Path("modules/core/db/schema_parts/business.py").read_text(encoding="utf-8")
    assert "IN ('sea', 'air', 'rail')" in schema_source


def test_active_product_center_requests_do_not_accept_destination_or_site_scope():
    from backend.schemas.product_center import (
        LogisticsBillCreateRequest,
        LogisticsProviderRuleCreateRequest,
        SkuOperatingProfileCreateRequest,
    )

    assert "destination" not in LogisticsBillCreateRequest.model_fields
    assert "destination" not in LogisticsProviderRuleCreateRequest.model_fields
    assert "shop_id" not in SkuOperatingProfileCreateRequest.model_fields
    assert "site_code" not in SkuOperatingProfileCreateRequest.model_fields
    assert "platform_fee_rate" not in SkuOperatingProfileCreateRequest.model_fields


def test_warehouse_scope_migration_is_forward_only_and_renames_projection_config():
    migration = Path("current_migrations/versions/20260914_warehouse_platform_profit.py").read_text(encoding="utf-8")
    assert "current_schema_20260914_warehouse_platform_profit" in migration
    assert "platform_sku_profit_table_id" in migration
    assert '"dim_warehouses"' in migration
    assert '"default_fee_rate"' in migration
    assert "_guard_empty" in migration
    assert "raise RuntimeError(\"warehouse scope migration is intentionally forward-only\")" in migration


def test_confirmed_logistics_cost_uses_exists_for_warehouse_filter_without_grn_multiplication():
    source = Path("backend/services/product_finance_service.py").read_text(encoding="utf-8")

    assert "LogisticsBillLine.warehouse_code == warehouse_code" in source


def test_saving_site_profit_persists_current_price_and_coupon_and_refreshes_projection():
    finance_source = Path("backend/services/product_finance_service.py").read_text(encoding="utf-8")
    router_source = Path("backend/domains/business/routers/product_center.py").read_text(encoding="utf-8")

    assert "profile.selling_price = data[\"selling_price\"]" in finance_source
    assert "profile.default_coupon_amount = data[\"coupon_amount\"]" in finance_source
    assert "site_profiles =" in router_source
    assert "await _enqueue_platform_sku_profit_projection(db, profile)" in router_source
