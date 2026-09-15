from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.schemas.product_center import (
    LogisticsBillCreateRequest,
    LogisticsBillLineRequest,
    LogisticsBillUpdateRequest,
    LogisticsProviderRuleUpdateRequest,
)


@pytest.mark.parametrize("request_type,payload", [
    (LogisticsBillCreateRequest, {"bill_no": "B-1", "bill_date": date(2026, 9, 16), "total_amount": 1, "currency": "USD"}),
    (LogisticsBillUpdateRequest, {"currency": "USD"}),
])
def test_logistics_bill_write_contract_rejects_non_cny(request_type, payload):
    with pytest.raises(ValidationError, match="CNY"):
        request_type(**payload)


@pytest.mark.parametrize(("basis", "unit"), [
    ("volume", "CNY/CBM"),
    ("weight", "CNY/KG"),
    ("quantity", "CNY/unit"),
    ("fixed", "CNY"),
])
def test_logistics_bill_line_uses_cny_unit_fixed_by_billing_basis(basis, unit):
    request = LogisticsBillLineRequest(
        sku_ids=[1], warehouse_code="WH-1", billing_basis=basis, line_total_amount=1
    )
    assert request.billing_unit == unit


def test_logistics_bill_line_rejects_unit_that_does_not_match_basis():
    with pytest.raises(ValidationError, match="billing_unit must be CNY/CBM"):
        LogisticsBillLineRequest(
            sku_ids=[1], warehouse_code="WH-1", billing_basis="volume",
            billing_unit="USD/CBM", line_total_amount=1,
        )


def test_logistics_provider_rule_patch_is_a_true_partial_request():
    request = LogisticsProviderRuleUpdateRequest(notes="rechecked")
    assert request.model_dump(exclude_unset=True) == {"notes": "rechecked"}


def test_logistics_provider_rule_patch_derives_unit_only_when_basis_changes():
    request = LogisticsProviderRuleUpdateRequest(billing_basis="weight")
    assert request.model_dump(exclude_unset=True) == {
        "billing_basis": "weight", "billing_unit": "CNY/KG"
    }


def test_finance_purchase_cost_queries_only_use_cny_or_cny_base_amount():
    source = Path("backend/services/product_finance_service.py").read_text(encoding="utf-8")
    purchase_section = source[source.index("async def find_latest_purchase_cost"):source.index("async def prefetch_platform_sku_profit_inputs")]
    prefetch_section = source[source.index("async def prefetch_platform_sku_profit_inputs"):source.index("actual_logistics: dict")]

    for section in (purchase_section, prefetch_section):
        assert "POLine.currency == \"CNY\"" in section
        assert "POLine.base_amt" in section
        assert "POLine.qty_ordered > 0" in section


def test_storage_rule_creation_locks_all_active_windows_and_rejects_overlap():
    source = Path("backend/domains/business/routers/product_center.py").read_text(encoding="utf-8")
    section = source[source.index("async def create_warehouse_storage_rule"):source.index("async def update_warehouse_storage_rule")]

    assert "WarehouseStorageRule.status == \"active\"" in section
    assert "with_for_update()" in section
    assert "existing_rule.effective_from <= new_effective_to" in section
    assert "body.effective_from <= existing_effective_to" in section
    assert "current_rule.effective_to = body.effective_from - timedelta(days=1)" in section


def test_product_center_sensitive_writes_emit_audit_logs_and_restrict_sales_fee_rates():
    source = Path("backend/domains/business/routers/product_center.py").read_text(encoding="utf-8")

    assert "from modules.core.db import (" in source
    assert "FactAuditLog," in source
    assert "async def _write_product_center_audit" in source
    assert source.count("await _write_product_center_audit(") >= 4
    fee_section = source[source.index("async def update_platform_fee_rate"):source.index('@router.get("/api/logistics-bills")')]
    assert 'row.platform_role != "sales"' in fee_section
