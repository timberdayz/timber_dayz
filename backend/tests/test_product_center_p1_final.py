from datetime import date
from decimal import Decimal
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


def test_reference_logistics_rule_uses_the_only_default_at_highest_specificity():
    """A configured default resolves same-priority provider tariffs deterministically."""
    from backend.services.product_finance_service import ProductFinanceService
    from modules.core.db import LogisticsProviderRule

    common = {
        "warehouse_code": "US-WH-1",
        "transport_type": "sea",
        "cargo_class": "normal",
        "is_sensitive": False,
    }
    first = LogisticsProviderRule(rule_id=1, logistics_provider="Provider A", **common)
    default = LogisticsProviderRule(
        rule_id=2, logistics_provider="Provider B", is_default=True, **common
    )

    assert (
        ProductFinanceService._select_reference_logistics_rule(
            [first, default], "US-WH-1", "sea"
        )
        is default
    )


def test_reference_logistics_rule_remains_unresolved_for_zero_or_multiple_defaults():
    from backend.services.product_finance_service import ProductFinanceService
    from modules.core.db import LogisticsProviderRule

    common = {
        "warehouse_code": "US-WH-1",
        "transport_type": "sea",
        "cargo_class": "normal",
        "is_sensitive": False,
    }
    first = LogisticsProviderRule(rule_id=1, logistics_provider="Provider A", **common)
    second = LogisticsProviderRule(rule_id=2, logistics_provider="Provider B", **common)
    assert ProductFinanceService._select_reference_logistics_rule(
        [first, second], "US-WH-1", "sea"
    ) is None

    first.is_default = True
    second.is_default = True
    assert ProductFinanceService._select_reference_logistics_rule(
        [first, second], "US-WH-1", "sea"
    ) is None


def test_logistics_provider_rule_default_is_part_of_create_and_patch_contracts():
    from backend.schemas.product_center import LogisticsProviderRuleCreateRequest

    create = LogisticsProviderRuleCreateRequest(
        logistics_provider="Provider A",
        effective_from=date(2026, 9, 19),
        is_default=True,
    )
    update = LogisticsProviderRuleUpdateRequest(is_default=False)

    assert create.is_default is True
    assert update.model_dump(exclude_unset=True) == {"is_default": False}


def test_default_provider_rule_has_a_forward_only_schema_migration():
    migration = Path(
        "current_migrations/versions/20260919_logistics_rule_default.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "current_schema_20260919_logistics_rule_default"' in migration
    assert 'down_revision = "current_schema_20260918_logistics_bill_currency_cny"' in migration
    assert '"is_default"' in migration
    assert "uq_logistics_provider_rules_default_scope" in migration


def test_feishu_projection_initialize_and_retry_are_audited_before_commit_without_credentials():
    source = Path("backend/domains/business/routers/product_center.py").read_text(
        encoding="utf-8"
    )
    endpoints = [
        (
            "async def initialize_feishu_projection",
            '@router.get("/api/feishu-projection/status")',
            'action_type="initialize"',
        ),
        (
            "async def retry_failed_feishu_projection",
            '@router.get("/api/spu-operating")',
            'action_type="retry"',
        ),
    ]
    for start, end, action in endpoints:
        section = source[source.index(start) : source.index(end)]
        assert "await _write_product_center_audit(" in section
        assert action in section
        assert 'resource_type="feishu_projection"' in section
        assert section.index("await _write_product_center_audit(") < section.index(
            "await db.commit()"
        )

    audit_sections = [
        source[source.index(start) : source.index(end)] for start, end, _action in endpoints
    ]
    for section in audit_sections:
        audit_call = section[section.index("await _write_product_center_audit(") :]
        assert "app_secret" not in audit_call.lower()
        assert "tenant_access_token" not in audit_call.lower()


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


def test_logistics_bill_header_is_cny_only_in_persistence_and_actual_cost_reads():
    from sqlalchemy import CheckConstraint

    from modules.core.db import LogisticsBill

    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in LogisticsBill.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert constraints["ck_logistics_bills_currency"] == "currency = 'CNY'"

    migration = Path(
        "current_migrations/versions/20260918_logistics_bill_currency_cny.py"
    ).read_text(encoding="utf-8")
    assert "currency <> 'CNY'" in migration
    assert "cannot enforce CNY logistics bill currency" in migration
    assert "ck_logistics_bills_currency" in migration

    source = Path("backend/services/product_finance_service.py").read_text(
        encoding="utf-8"
    )
    single_lookup = source[
        source.index("async def find_confirmed_logistics_cost"):
        source.index("async def find_reference_logistics_cost")
    ]
    bulk_lookup = source[
        source.index("async def prefetch_platform_sku_profit_inputs"):
        source.index("async def preview_profit")
    ]
    assert single_lookup.count('LogisticsBill.currency == "CNY"') == 2
    assert bulk_lookup.count('LogisticsBill.currency == "CNY"') == 2


def test_compatibility_operating_profile_writes_and_preview_reject_non_sales_platforms():
    router_source = Path("backend/domains/business/routers/product_center.py").read_text(
        encoding="utf-8"
    )
    dimensions = router_source[
        router_source.index("async def _validate_operating_dimensions"):
        router_source.index('@router.post("/api/sku-operating-profiles"')
    ]
    assert 'platform is None or not platform.is_active or platform.platform_role != "sales"' in dimensions

    service_source = Path("backend/services/product_finance_service.py").read_text(
        encoding="utf-8"
    )
    preview = service_source[
        service_source.index("async def preview_operating_profit"):
        service_source.index("async def preview_platform_sku_profit")
    ]
    assert 'platform is None or not platform.is_active or platform.platform_role != "sales"' in preview


def test_compatibility_operating_profile_writes_are_audited_in_the_committing_transaction():
    source = Path("backend/domains/business/routers/product_center.py").read_text(
        encoding="utf-8"
    )
    endpoint_bounds = [
        ("async def create_sku_operating_profile", '@router.patch("/api/sku-operating-profiles/{profile_id}"'),
        ("async def update_sku_operating_profile", '@router.post("/api/sku-operating-profiles/bulk")'),
        ("async def bulk_save_sku_operating_profiles", '@router.get("/api/sku-operating-profiles/{profile_id}"'),
        ("async def save_sku_operating_profit", '@router.get("/api/sku-operating-profiles/{profile_id}/profit-estimates"'),
    ]
    for start, end in endpoint_bounds:
        section = source[source.index(start):source.index(end)]
        audit_index = section.index("await _write_product_center_audit(")
        assert audit_index < section.index("await db.commit()"), start


def test_product_master_and_legacy_profit_writes_are_audited_before_commit():
    """All product-center write paths must persist audit rows atomically."""
    source = Path("backend/domains/business/routers/product_center.py").read_text(
        encoding="utf-8"
    )
    endpoint_bounds = [
        ("async def create_spu", '@router.patch("/api/spus/{spu}"'),
        ("async def update_spu", '@router.post("/api/spus/bulk"'),
        ("async def bulk_save_spus", '@router.get("/api/skus"'),
        ("async def create_sku", '@router.patch("/api/skus/{sku_id}"'),
        ("async def update_sku", 'async def _apply_bulk_sku_spu_binding'),
        ("async def bulk_save_skus", '@router.get("/api/spus/{spu}/skus"'),
        ("async def create_cost_assumption", '@router.patch("/api/cost-assumption-profiles/{profile_id}"'),
        ("async def update_cost_assumption", 'def _serialize_bill'),
        ("async def create_profit_estimate", "async def save_baseline_product_profit"),
        ("async def save_baseline_product_profit", "async def initialize_feishu_projection"),
    ]
    for start, end in endpoint_bounds:
        section = source[source.index(start):source.index(end)]
        assert "await _write_product_center_audit(" in section, start
        assert section.index("await _write_product_center_audit(") < section.index(
            "await db.commit()"
        ), start


def test_product_category_writes_are_audited_atomically_with_category_identity_and_changes():
    """Category mutations must leave an auditable record in their committing transaction."""
    source = Path("backend/domains/business/routers/product_center.py").read_text(
        encoding="utf-8"
    )
    endpoint_bounds = [
        ("async def create_product_category", '@router.patch("/api/product-categories/{category_code}"'),
        ("async def update_product_category", "async def _apply_spu_category"),
    ]
    for start, end in endpoint_bounds:
        section = source[source.index(start):source.index(end)]
        audit_index = section.index("await _write_product_center_audit(")
        assert audit_index < section.index("await db.commit()"), start
        assert 'resource_type="product_category"' in section
        assert "resource_id=row.category_code" in section
        assert "changes=" in section


def test_platform_profit_save_only_persists_actual_recost_when_actual_cost_exists():
    """Missing reference data must not manufacture an actual-cost estimate version."""
    source = Path("backend/domains/business/routers/product_center.py").read_text(
        encoding="utf-8"
    )
    section = source[
        source.index("async def save_platform_sku_profit_estimates"):
        source.index('@router.get("/api/platform-sku-profit/estimates")')
    ]
    assert "preview.get(\"actual_logistics_cost\") is not None" in section
    assert "preview.get(\"actual_storage_cost\") is not None" in section
    assert 'versions.append(("actual_recost", preview["actual_recost"]))' in section
    assert 'preview["actual_recost"].get("completeness") != "estimated"' not in section


def test_spu_sku_binding_audits_both_historical_and_new_effective_bindings_before_commit():
    """A rebinding must preserve effective-dated lineage in the audit transaction."""
    source = Path("backend/domains/business/routers/product_center.py").read_text(
        encoding="utf-8"
    )
    section = source[
        source.index("async def bind_spu_sku"):
        source.index('@router.get("/api/purchase-orders")')
    ]

    assert section.count("await _write_product_center_audit(") == 2
    assert 'action_type="update"' in section
    assert 'action_type="create"' in section
    assert section.count('resource_type="spu_sku_binding"') == 2
    assert 'resource_id=f"{current_binding.spu}:{current_binding.sku_id}"' in section
    assert 'resource_id=f"{row.spu}:{row.sku_id}"' in section
    assert '"effective_from": current_binding.effective_from' in section
    assert '"effective_to": body.effective_from' in section
    assert '"binding_status": "historical"' in section
    assert '"effective_from": row.effective_from' in section
    assert '"effective_to": row.effective_to' in section
    assert '"binding_status": row.binding_status' in section
    assert section.index("await _write_product_center_audit(") < section.index(
        "await db.commit()"
    )
    assert "BridgeErpSkuKey" not in section


def test_product_warehouse_writes_are_audited_in_the_committing_transaction():
    source = Path("backend/domains/business/routers/product_center.py").read_text(
        encoding="utf-8"
    )
    endpoint_bounds = [
        ("async def create_product_warehouse", '@router.patch("/api/product-warehouses/{warehouse_code}"'),
        ("async def update_product_warehouse", '@router.patch("/api/platforms/{platform_code}/fee-rate"'),
    ]
    for start, end in endpoint_bounds:
        section = source[source.index(start):source.index(end)]
        audit_index = section.index("await _write_product_center_audit(")
        assert audit_index < section.index("await db.commit()"), start


def test_product_center_audit_helper_records_identity_fields_without_secrets():
    source = Path("backend/domains/business/routers/product_center.py").read_text(
        encoding="utf-8"
    )
    helper = source[source.index("async def _write_product_center_audit"):source.index("def _decimal_payload")]
    for field in ("user_id", "username", "action_type", "resource_type", "resource_id"):
        assert field in helper
    assert "password" not in helper.lower()
    assert "secret" not in helper.lower()


def test_direct_sku_volume_is_the_primary_reference_cost_measurement():
    from modules.core.db import DimErpSku
    from backend.services.product_finance_service import _reference_unit_volume_cbm

    sku = DimErpSku(unit_volume_cbm=0.0125)
    assert _reference_unit_volume_cbm(sku).as_tuple() == Decimal("0.0125").as_tuple()

    legacy = DimErpSku(package_length_cm=20, package_width_cm=10, package_height_cm=5)
    assert _reference_unit_volume_cbm(legacy).as_tuple() == Decimal("0.001").as_tuple()


def test_platform_profit_version_refuses_incomplete_inputs_with_structured_missing_fields():
    source = Path("backend/domains/business/routers/product_center.py").read_text(encoding="utf-8")
    section = source[
        source.index("async def save_platform_sku_profit_estimates"):
        source.index('@router.get("/api/platform-sku-profit/estimates")')
    ]
    assert "cannot_save_profit_version" in section
    assert "missing_fields" in section
    assert "status_code=422" in section


def test_platform_profit_draft_is_distinct_from_immutable_profit_versions():
    source = Path("backend/domains/business/routers/product_center.py").read_text(encoding="utf-8")
    schema = Path("backend/schemas/product_center.py").read_text(encoding="utf-8")
    assert '"/api/platform-sku-profit/drafts"' in source
    assert "PlatformSkuProfitDraftRequest" in schema
    assert "PlatformSkuProfitDraft" in source


def test_storage_rule_patch_accepts_material_changes_as_a_new_version():
    schema = Path("backend/schemas/product_center.py").read_text(encoding="utf-8")
    source = Path("backend/domains/business/routers/product_center.py").read_text(encoding="utf-8")
    assert "unit_rate_cny: Optional[float]" in schema
    assert "effective_from: Optional[date]" in schema
    section = source[
        source.index("async def update_warehouse_storage_rule"):
        source.index("async def create_product_warehouse")
    ]
    assert "WarehouseStorageRule(" in section
    assert "storage_rule_versioned" in section


def test_storage_rule_version_window_is_validated_by_request_and_database_contract():
    with pytest.raises(ValidationError, match="effective_to"):
        WarehouseStorageRuleUpdateRequest(
            unit_rate_cny=100,
            effective_from=date(2026, 9, 20),
            effective_to=date(2026, 9, 19),
        )
    source = Path("modules/core/db/schema_parts/business.py").read_text(encoding="utf-8")
    migration = Path("current_migrations/versions/20260920_sku_direct_volume_and_profit_drafts.py").read_text(encoding="utf-8")
    assert "ck_warehouse_storage_rules_window" in source
    assert "ck_warehouse_storage_rules_window" in migration


def test_platform_profit_draft_reuses_operating_scope_validation():
    source = Path("backend/domains/business/routers/product_center.py").read_text(encoding="utf-8")
    section = source[
        source.index("async def save_platform_sku_profit_draft"):
        source.index("async def save_platform_sku_profit_estimates")
    ]
    assert "await _validate_operating_dimensions(db, values)" in section
    assert "except IntegrityError" in section
