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

    candidate = PersonalPerformanceWorkbenchService._candidate_employee(employee, [], {})

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
