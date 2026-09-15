from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.schemas.product_center import (
    LogisticsBillCreateRequest,
    LogisticsBillLineRequest,
    LogisticsBillLinesReplaceRequest,
    LogisticsBillSkuLineRequest,
    LogisticsBillUpdateRequest,
    LogisticsProviderRuleUpdateRequest,
    WarehouseStorageRuleUpdateRequest,
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


def test_finance_purchase_cost_queries_require_positive_cny_base_amount_for_foreign_currency():
    source = Path("backend/services/product_finance_service.py").read_text(encoding="utf-8")
    purchase_section = source[source.index("async def find_latest_purchase_cost"):source.index("async def prefetch_platform_sku_profit_inputs")]
    prefetch_section = source[source.index("async def prefetch_platform_sku_profit_inputs"):source.index("actual_logistics: dict")]

    for section in (purchase_section, prefetch_section):
        # CNY lines use their unit price. Foreign-currency lines are only CNY
        # costs after a positive converted base amount is present.
        assert "POLine.currency == \"CNY\"" in section
        assert "POLine.unit_price" in section
        assert "POLine.base_amt" in section
        assert "POLine.base_amt > 0" in section
        assert "POLine.qty_ordered > 0" in section


def test_candidate_purchase_cost_falls_back_only_when_foreign_base_cost_is_missing():
    router_source = Path("backend/domains/business/routers/product_center.py").read_text(encoding="utf-8")
    candidate_section = router_source[
        router_source.index("async def list_platform_sku_profit_candidates"):
        router_source.index('@router.post("/api/platform-sku-profit/preview")')
    ]

    # The prefetch map contains only valid CNY-derived costs. A missing foreign
    # conversion must therefore use the SKU default, or remain incomplete.
    assert 'purchase_cost = cost_inputs["purchase_cost"] or row.default_purchase_cost' in candidate_section
    assert 'purchase_cost=purchase_cost' in candidate_section


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


def test_storage_rule_patch_never_reactivates_historical_or_stopped_rule():
    source = Path("backend/domains/business/routers/product_center.py").read_text(encoding="utf-8")
    section = source[
        source.index("async def update_warehouse_storage_rule"):
        source.index('@router.post("/api/product-warehouses"')
    ]

    assert 'values.get("status") == "active"' in section
    assert 'row.status != "active"' in section
    assert "create a new storage rule version" in section


def test_legacy_single_sku_bill_line_normalizes_to_cny_volume_contract():
    request = LogisticsBillLinesReplaceRequest(
        lines=[LogisticsBillSkuLineRequest(sku_id=1, warehouse_code="WH-1", shipped_qty=2)]
    )
    line = request.lines[0]

    assert line.billing_basis == "volume"
    assert line.billing_unit == "CNY/CBM"


def test_bill_line_service_defensively_normalizes_legacy_cny_unit():
    source = Path("backend/services/product_finance_service.py").read_text(encoding="utf-8")
    section = source[
        source.index("async def replace_bill_lines"):
        source.index("async def replace_bill_purchase_orders")
    ]

    assert 'basis = line.get("billing_basis") or "volume"' in section
    assert 'billing_unit = _CNY_BILLING_UNITS[basis]' in section
    assert "billing_unit=billing_unit" in section


def test_logistics_bill_line_persistence_rejects_null_or_non_cny_units():
    from sqlalchemy import CheckConstraint

    from modules.core.db import LogisticsBillLine

    assert LogisticsBillLine.__table__.c.billing_unit.nullable is False
    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in LogisticsBillLine.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "ck_logistics_bill_lines_cny_billing_unit" in constraints
    assert "CNY/CBM" in constraints["ck_logistics_bill_lines_cny_billing_unit"]

    migration = Path(
        "current_migrations/versions/20260917_logistics_bill_line_cny_units.py"
    ).read_text(encoding="utf-8")
    assert "billing_unit IS NULL" in migration
    assert "nullable=False" in migration


def test_logistics_bill_writes_are_audited_once_by_canonical_endpoints():
    source = Path("backend/domains/business/routers/product_center.py").read_text(encoding="utf-8")
    endpoint_bounds = [
        ("async def supplement_purchase_order_line_cost", '@router.get("/api/purchase-orders/{po_id}")'),
        ("async def create_logistics_provider_rule", '@router.patch("/api/logistics-provider-rules/{rule_id}")'),
        ("async def update_logistics_provider_rule", '@router.get("/api/cost-assumption-profiles")'),
        ("async def create_logistics_bill", '@router.post("/api/logistics-batches", status_code=201)'),
        ("async def replace_logistics_bill_purchase_orders", '@router.put("/api/logistics-batches/{bill_id}/purchase-orders")'),
        ("async def update_logistics_bill", '@router.patch("/api/logistics-batches/{bill_id}")'),
        ("async def replace_logistics_bill_lines", '@router.put("/api/logistics-batches/{bill_id}/lines")'),
        ("async def confirm_logistics_bill", '@router.post("/api/logistics-batches/{bill_id}/confirm")'),
        ("async def void_logistics_bill", '@router.post("/api/logistics-batches/{bill_id}/void")'),
    ]

    for start, end in endpoint_bounds:
        section = source[source.index(start):source.index(end)]
        assert "await _write_product_center_audit(" in section, start

    for alias in (
        "async def create_logistics_batch",
        "async def replace_logistics_batch_purchase_orders",
        "async def update_logistics_batch",
        "async def replace_logistics_batch_lines",
        "async def confirm_logistics_batch",
        "async def void_logistics_batch",
    ):
        section = source[source.index(alias):source.find("\n@router", source.index(alias) + 1)]
        assert "_write_product_center_audit" not in section, alias
