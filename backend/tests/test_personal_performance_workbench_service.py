from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.personal_performance_workbench_service import (
    PersonalPerformanceWorkbenchService,
)


class _ScalarOneResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _CatalogRowsResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


def _catalog_metric():
    return SimpleNamespace(
        metric_code="attendance_compliance_rate",
        metric_name="Attendance",
        metric_direction="higher_better",
        input_kind="percentage",
        default_target_value=100,
        unit="%",
        sort_key=1,
        guidance="Enter actual attendance rate.",
        scoring_rule_version="controlled_targets_v1",
        catalog_version=1,
    )


@pytest.mark.asyncio
async def test_get_workbench_marks_an_empty_month_as_creatable_not_legacy_read_only():
    db = SimpleNamespace()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneResult(None),
            _ScalarOneResult(1),
            _CatalogRowsResult([_catalog_metric()]),
            _ScalarOneResult(None),
            _ScalarOneResult(None),
        ]
    )

    payload = await PersonalPerformanceWorkbenchService(db).get_workbench("2026-09")

    assert payload["calculation_mode"] == "legacy_inputs"
    assert payload["legacy_read_only"] is False
    assert payload["has_legacy_records"] is False


@pytest.mark.asyncio
async def test_get_workbench_marks_active_legacy_records_as_read_only():
    db = SimpleNamespace()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneResult(None),
            _ScalarOneResult(1),
            _CatalogRowsResult([_catalog_metric()]),
            _ScalarOneResult(None),
            _ScalarOneResult(99),
        ]
    )

    payload = await PersonalPerformanceWorkbenchService(db).get_workbench("2026-07")

    assert payload["calculation_mode"] == "legacy_inputs"
    assert payload["legacy_read_only"] is True
    assert payload["has_legacy_records"] is True


@pytest.mark.asyncio
async def test_get_workbench_keeps_a_controlled_plan_writable_contract():
    service = PersonalPerformanceWorkbenchService(SimpleNamespace())
    service._plan = AsyncMock(
        return_value=SimpleNamespace(
            version=3,
            scope_confirmed_at=None,
            rule_snapshot={"metrics": [{"metric_code": "attendance_compliance_rate"}]},
        )
    )

    payload = await service.get_workbench("2026-09")

    assert payload == {
        "year_month": "2026-09",
        "calculation_mode": "controlled_targets_v1",
        "plan_version": 3,
        "scope_confirmed": False,
        "metrics": [{"metric_code": "attendance_compliance_rate"}],
        "legacy_read_only": False,
        "has_legacy_records": False,
    }


def test_scope_eligibility_requires_positive_assignment_ratio_and_sales_target():
    assignment = SimpleNamespace(
        platform_code="Shopee", shop_id="S001", target_allocation_ratio=0.5
    )
    zero_ratio = SimpleNamespace(
        platform_code="Shopee", shop_id="S002", target_allocation_ratio=0
    )
    targets = {("shopee", "S001"): SimpleNamespace(target_amount=100)}

    assert PersonalPerformanceWorkbenchService._eligibility([assignment], targets) == ["shopee/S001"]
    assert PersonalPerformanceWorkbenchService._eligibility([zero_ratio], targets) == []
    assert PersonalPerformanceWorkbenchService._eligibility([assignment], {}) == []


def test_mixed_store_assignments_block_employee_and_identify_invalid_target_shop():
    valid_assignment = SimpleNamespace(
        platform_code="Shopee", shop_id="S001", target_allocation_ratio=0.5
    )
    invalid_assignment = SimpleNamespace(
        platform_code="Shopee", shop_id="S002", target_allocation_ratio=0.5
    )
    employee = SimpleNamespace(employee_code="EMP001", name="Ada")
    targets = {("shopee", "S001"): SimpleNamespace(target_amount=100)}

    assert (
        PersonalPerformanceWorkbenchService._eligibility(
            [valid_assignment, invalid_assignment], targets
        )
        == []
    )
    candidate = PersonalPerformanceWorkbenchService._candidate_employee(
        employee, None, None, [valid_assignment, invalid_assignment], targets
    )
    assert candidate["eligibility_status"] == "blocked"
    assert "shopee/S002" in candidate["blocking_reasons"][0]


def test_scope_candidate_blocks_employee_without_eligible_store_basis():
    employee = SimpleNamespace(employee_code=" EMP001 ", name="Ada")

    candidate = PersonalPerformanceWorkbenchService._candidate_employee(
        employee, None, None, [], {}
    )

    assert candidate["employee_code"] == "EMP001"
    assert candidate["eligibility_status"] == "blocked"
    assert candidate["is_included"] is False
    assert candidate["blocking_reasons"]


def test_entry_payload_rejects_wrong_fields_and_normalizes_special_task_note():
    percentage = {"input_kind": "percentage"}
    with pytest.raises(ValueError, match="百分比"):
        PersonalPerformanceWorkbenchService._entry_payload(
            SimpleNamespace(actual_value=90, completed_count=1, required_count=None, result=None, note=None),
            percentage,
        )

    task = {"input_kind": "special_task"}
    payload = PersonalPerformanceWorkbenchService._entry_payload(
        SimpleNamespace(actual_value=None, completed_count=None, required_count=None, result="partial", note="  follow up  "),
        task,
    )
    assert payload == {"result": "partial", "note": "follow up"}


def test_blank_employee_identifier_is_rejected():
    with pytest.raises(ValueError, match="不能为空"):
        PersonalPerformanceWorkbenchService._clean_code("  ")


def test_sales_target_query_uses_requested_month_overlap_and_deterministic_priority():
    from datetime import date

    conditions, ordering = PersonalPerformanceWorkbenchService._sales_target_query_parts(
        "2026-07"
    )

    rendered = " ".join(str(condition) for condition in conditions)
    assert "period_start" in rendered
    assert "period_end" in rendered
    assert date(2026, 7, 1)
    assert len(ordering) >= 2


def test_employee_snapshot_includes_department_and_position_names():
    employee = SimpleNamespace(employee_code="EMP001", name="Ada")
    department = SimpleNamespace(department_name="Operations")
    position = SimpleNamespace(position_name="Manager")

    snapshot = PersonalPerformanceWorkbenchService._employee_snapshot(
        employee, department, position
    )

    assert snapshot["department_name"] == "Operations"
    assert snapshot["position_name"] == "Manager"


def test_revoke_scope_requires_expected_plan_version():
    import inspect

    signature = inspect.signature(PersonalPerformanceWorkbenchService.revoke_scope)
    assert "expected_plan_version" in signature.parameters


def test_zero_amount_authoritative_target_does_not_fall_back_to_older_positive_target():
    current_zero = SimpleNamespace(
        platform_code="shopee", shop_id="S001", target_amount=0, target_id=20
    )
    old_positive = SimpleNamespace(
        platform_code="shopee", shop_id="S001", target_amount=100, target_id=10
    )

    selected = PersonalPerformanceWorkbenchService._select_authoritative_sales_targets(
        [current_zero, old_positive]
    )

    assert selected == {}


@pytest.mark.asyncio
async def test_month_transaction_lock_is_acquired_before_mutability_check(monkeypatch):
    import backend.services.personal_performance_workbench_service as module

    calls = []

    class Lock:
        def __init__(self, _db):
            pass

        async def acquire_month_transaction_lock(self, *, year_month):
            calls.append(("lock", year_month))

        async def assert_month_mutable(self, *, year_month):
            calls.append(("mutable", year_month))

    monkeypatch.setattr(module, "PayrollPeriodLockService", Lock)
    service = PersonalPerformanceWorkbenchService(SimpleNamespace())

    await service._begin_month_mutation("2026-07")

    assert calls == [("lock", "2026-07"), ("mutable", "2026-07")]


@pytest.mark.asyncio
async def test_month_commit_rechecks_payroll_lock_before_commit(monkeypatch):
    import backend.services.personal_performance_workbench_service as module

    calls = []

    class Lock:
        def __init__(self, _db):
            pass

        async def assert_month_mutable(self, *, year_month):
            calls.append(("mutable", year_month))

    db = SimpleNamespace()

    async def commit():
        calls.append(("commit", None))

    db.commit = commit
    monkeypatch.setattr(module, "PayrollPeriodLockService", Lock)

    await PersonalPerformanceWorkbenchService(db)._commit_month_mutation("2026-07")

    assert calls == [("mutable", "2026-07"), ("commit", None)]
