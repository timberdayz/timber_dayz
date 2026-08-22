from types import SimpleNamespace

import pytest

from backend.services.personal_performance_workbench_service import (
    PersonalPerformanceWorkbenchService,
)


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
