from decimal import Decimal
from pathlib import Path
from sqlalchemy import inspect

from backend.schemas.product_center import (
    PlatformSkuProfitPreviewRequest,
    WarehouseStorageRuleCreateRequest,
    WarehouseStorageRuleUpdateRequest,
)
from modules.core.db import DimErpSku, DimPlatform
from modules.core.db.schema_parts.business import WarehouseStorageRule
from backend.services.product_profit_service import build_reference_storage_cost


def test_turnover_class_and_platform_role_are_in_schema():
    assert "turnover_class" in {c.name for c in inspect(DimErpSku).columns}
    assert "platform_role" in {c.name for c in inspect(DimPlatform).columns}


def test_reference_storage_cost_uses_turnover_days_and_cny_per_cbm():
    assert build_reference_storage_cost(
        unit_volume_cbm=Decimal("0.02"),
        unit_rate_cny_per_cbm_month=Decimal("300"),
        turnover_class="normal",
    ) == Decimal("12.00")


def test_turnover_class_rejects_unknown_values():
    checks = [c.sqltext.text for c in DimErpSku.__table__.constraints if getattr(c, "sqltext", None) is not None]
    assert any("turnover_class" in text and "fast" in text and "normal" in text and "slow" in text for text in checks)


def test_storage_rule_is_volume_cny_contract():
    columns = {c.name for c in inspect(WarehouseStorageRule).columns}
    assert {"warehouse_code", "billing_basis", "billing_unit", "unit_rate_cny"} <= columns
    assert "reference_storage_days" not in columns


def test_storage_rule_requests_do_not_accept_manual_reference_days():
    assert "reference_storage_days" not in WarehouseStorageRuleCreateRequest.model_fields
    assert "reference_storage_days" not in WarehouseStorageRuleUpdateRequest.model_fields


def test_platform_profit_preview_requires_explicit_transport_type():
    try:
        PlatformSkuProfitPreviewRequest(
            sku_id=1,
            platform_code="shopee",
            warehouse_code="US-WH",
        )
    except ValueError as exc:
        assert "transport_type" in str(exc)
    else:
        raise AssertionError("transport_type must be selected explicitly")


def test_platform_profit_preview_rejects_manual_reference_costs():
    try:
        PlatformSkuProfitPreviewRequest(
            sku_id=1,
            platform_code="shopee",
            warehouse_code="US-WH",
            transport_type="sea",
            expected_logistics_cost=10,
        )
    except ValueError as exc:
        assert "expected_logistics_cost" in str(exc)
    else:
        raise AssertionError("reference costs must come from rules, not request input")


def test_reference_logistics_falls_back_only_when_the_best_rule_is_unambiguous():
    source = Path("backend/services/product_finance_service.py").read_text(encoding="utf-8")

    assert "LogisticsProviderRule.warehouse_code.is_(None)" in source
    assert "LogisticsProviderRule.transport_type.is_(None)" in source
    assert "if len(best_rules) != 1:" in source


def test_current_schema_migration_adds_cny_storage_and_turnover_contracts():
    migration = Path("current_migrations/versions/20260916_sku_turnover_storage_rules_cny.py").read_text(encoding="utf-8")

    assert 'revision = "current_schema_20260916_sku_turnover_storage_rules_cny"' in migration
    assert '"warehouse_storage_rules"' in migration
    assert '"turnover_class"' in migration
    assert '"platform_role"' in migration
    assert "CNY/CBM/month" in migration
    assert 'sa.Column("reference_storage_days", sa.Integer(), nullable=True)' in migration


def test_operating_dimensions_expose_current_spu_and_sales_fee_metadata():
    source = Path("backend/domains/business/routers/product_center.py").read_text(encoding="utf-8")

    assert '"spu": spu_by_sku.get(row.sku_id)' in source
    assert 'DimPlatform.platform_role == "sales"' in source
    assert '"default_fee_rate": row.default_fee_rate' in source
    assert '"fee_rate_effective_from": row.fee_rate_effective_from' in source
    assert '"fee_rate_source": row.fee_rate_source' in source
    assert '"fee_rate_version": row.fee_rate_version' in source
    schema = Path("backend/schemas/product_center.py").read_text(encoding="utf-8")
    assert "class SkuOperatingPlatformOption" in schema
    assert "fee_rate_effective_from: Optional[date]" in schema


def test_sku_contract_exposes_turnover_and_purchase_cost_confirmation():
    source = Path("backend/schemas/product_center.py").read_text(encoding="utf-8")

    assert "purchase_cost_confirmed_at" in source
    assert "turnover_class" in source
    assert "SKU product-center amounts must use CNY" in source
