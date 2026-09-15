from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.schemas.product_center import (
    LogisticsProviderRuleCreateRequest,
    PurchaseOrderLineCostSupplementRequest,
    SkuBulkItem,
    SkuUpdateRequest,
    WarehouseStorageRuleCreateRequest,
    WarehouseStorageRuleUpdateRequest,
)


@pytest.mark.parametrize(
    ("factory", "payload"),
    [
        (SkuBulkItem, {"sku_key": "SKU-1", "purchase_cost_currency": "USD"}),
        (SkuBulkItem, {"sku_key": "SKU-1", "selling_price_currency": "USD"}),
        (SkuUpdateRequest, {"purchase_cost_currency": "USD"}),
        (SkuUpdateRequest, {"selling_price_currency": "USD"}),
        (PurchaseOrderLineCostSupplementRequest, {"unit_price": 1, "currency": "USD"}),
    ],
)
def test_product_center_cost_write_contract_rejects_non_cny(factory, payload):
    with pytest.raises(ValidationError, match="CNY"):
        factory(**payload)


@pytest.mark.parametrize(
    ("basis", "unit"),
    [
        ("volume", "CNY/CBM"),
        ("weight", "CNY/KG"),
        ("quantity", "CNY/unit"),
        ("fixed", "CNY"),
    ],
)
def test_logistics_rule_derives_cny_billing_unit_from_its_basis(basis, unit):
    rule = LogisticsProviderRuleCreateRequest(
        logistics_provider="Provider",
        billing_basis=basis,
        billing_unit=unit,
        effective_from=date(2026, 9, 16),
    )
    assert rule.billing_unit == unit


def test_logistics_rule_rejects_non_cny_billing_unit():
    with pytest.raises(ValidationError, match="CNY"):
        LogisticsProviderRuleCreateRequest(
            logistics_provider="Provider",
            billing_basis="volume",
            billing_unit="USD/CBM",
            effective_from=date(2026, 9, 16),
        )


def test_storage_rule_update_versions_a_published_tariff_or_window():
    fields = WarehouseStorageRuleUpdateRequest.model_fields
    assert "unit_rate_cny" in fields
    assert "effective_from" in fields
    assert "effective_to" in fields
    source = Path("backend/domains/business/routers/product_center.py").read_text(encoding="utf-8")
    section = source[
        source.index("async def update_warehouse_storage_rule"):
        source.index("async def create_product_warehouse")
    ]
    assert "storage_rule_versioned" in section
    assert "WarehouseStorageRule(" in section


def test_storage_rule_create_rejects_an_invalid_effective_window():
    with pytest.raises(ValidationError, match="effective_to"):
        WarehouseStorageRuleCreateRequest(
            warehouse_code="US-WH",
            unit_rate_cny=300,
            effective_from=date(2026, 9, 16),
            effective_to=date(2026, 9, 15),
        )


def test_platform_role_defaults_unknown_platforms_to_source_in_orm_and_migration():
    dimensions = Path("modules/core/db/schema_parts/dimensions.py").read_text(encoding="utf-8")
    migration = Path("current_migrations/versions/20260916_sku_turnover_storage_rules_cny.py").read_text(encoding="utf-8")

    assert 'default="source", server_default="source"' in dimensions
    assert 'server_default="source"' in migration
    assert "UPDATE core.dim_platforms SET platform_role = 'source'" in migration
    assert "WHERE platform_code IN ('shopee', 'tiktok', 'amazon')" in migration


def test_storage_rule_write_uses_platform_fee_permissions_and_versions_current_rule():
    source = Path("backend/domains/business/routers/product_center.py").read_text(encoding="utf-8")

    assert "_user=Depends(_require_platform_fee_editor)" in source
    assert "with_for_update()" in source
    assert "timedelta(days=1)" in source
    assert "effective_to = body.effective_from - timedelta(days=1)" in source


def test_storage_rule_patch_only_accepts_governance_fields():
    request = WarehouseStorageRuleUpdateRequest(status="inactive", source="finance", version="v2")
    assert request.model_dump(exclude_unset=True) == {
        "status": "inactive",
        "source": "finance",
        "version": "v2",
    }


def test_candidate_list_uses_bulk_prefetch_and_returns_a_preview():
    source = Path("backend/domains/business/routers/product_center.py").read_text(encoding="utf-8")
    candidate_source = source[source.index("async def list_platform_sku_profit_candidates"):source.index('@router.post("/api/platform-sku-profit/preview")')]

    assert "prefetch_platform_sku_profit_inputs" in candidate_source
    assert '"preview": _decimal_payload(preview)' in candidate_source
    assert "await finance.find_latest_purchase_cost(row)" not in candidate_source
    assert "await finance.find_reference_logistics_cost(row" not in candidate_source
    assert "await finance.find_reference_storage_cost(row" not in candidate_source
    assert "await finance.find_confirmed_logistics_cost(row" not in candidate_source


def test_candidates_keep_missing_inputs_incomplete_instead_of_zeroing_costs():
    source = Path("backend/services/product_profit_service.py").read_text(encoding="utf-8")

    assert "def optional_money(value" in source
    assert 'return None' in source[source.index("def calculated_profit"):source.index("selling_price = optional_money")]
