from datetime import datetime, timezone

import pytest
from pydantic import ValidationError


def test_personal_target_models_have_monthly_identity_and_historical_snapshots():
    from modules.core.db import (
        PersonalPerformanceAssignmentSnapshot,
        PersonalPerformanceEmployeeScope,
        PersonalPerformanceEntry,
        PersonalPerformanceMetricCatalog,
        PersonalPerformancePlan,
    )

    catalog = PersonalPerformanceMetricCatalog.__table__
    plan = PersonalPerformancePlan.__table__
    scope = PersonalPerformanceEmployeeScope.__table__
    assignment = PersonalPerformanceAssignmentSnapshot.__table__
    entry = PersonalPerformanceEntry.__table__

    assert catalog.schema == "a_class"
    assert {"catalog_version", "metric_code", "input_kind", "sort_key"}.issubset(
        catalog.c.keys()
    )
    assert any(
        constraint.name == "uq_personal_performance_metric_catalog_version_code"
        for constraint in catalog.constraints
    )

    assert plan.c.calculation_mode.nullable is False
    assert plan.c.rule_snapshot.nullable is False
    assert plan.c.version.nullable is False
    assert any(
        constraint.name == "uq_personal_performance_plan_month"
        for constraint in plan.constraints
    )

    assert scope.c.employee_name_snapshot.nullable is False
    assert scope.c.snapshot_version.nullable is False
    assert scope.c.exclusion_note.nullable is True
    assert any(
        constraint.name == "uq_personal_performance_scope_plan_employee"
        for constraint in scope.constraints
    )

    assert {
        "scope_id",
        "platform_code",
        "shop_id",
        "assignment_ratio_snapshot",
        "sales_target_amount_snapshot",
        "sales_target_breakdown_id_snapshot",
    }.issubset(assignment.c.keys())
    assert any(
        constraint.name == "uq_personal_performance_assignment_snapshot_scope_shop"
        for constraint in assignment.constraints
    )

    assert {"scope_id", "metric_code", "input_payload", "metric_snapshot"}.issubset(
        entry.c.keys()
    )
    assert any(
        constraint.name == "uq_personal_performance_entry_scope_metric"
        for constraint in entry.constraints
    )


def test_personal_workbench_response_exposes_legacy_read_only_state():
    from backend.schemas.hr import PersonalPerformanceWorkbenchResponse

    response = PersonalPerformanceWorkbenchResponse(
        year_month="2026-09",
        legacy_read_only=False,
        has_legacy_records=False,
    )

    assert response.legacy_read_only is False
    assert response.has_legacy_records is False


def test_personal_target_plan_restricts_the_controlled_mode_and_immutable_mode_contract():
    from modules.core.db import PersonalPerformancePlan

    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in PersonalPerformancePlan.__table__.constraints
        if getattr(constraint, "name", None)
        and hasattr(constraint, "sqltext")
    }

    assert "chk_personal_performance_plan_controlled_mode" in checks
    assert "controlled_targets_v1" in checks[
        "chk_personal_performance_plan_controlled_mode"
    ]


def test_personal_scope_contract_allows_an_empty_optional_exclusion_note():
    from backend.schemas.hr import PersonalPerformanceScopeApplyRequest

    request = PersonalPerformanceScopeApplyRequest(
        year_month="2026-09",
        expected_plan_version=1,
        employees=[{"employee_code": "EMP001", "is_included": False}],
    )

    assert request.employees[0].exclusion_note is None


def test_personal_rule_contract_rejects_duplicate_metric_codes():
    from backend.schemas.hr import PersonalPerformanceWorkbenchApplyRequest

    with pytest.raises(ValidationError, match="personal metrics cannot repeat"):
        PersonalPerformanceWorkbenchApplyRequest(
            year_month="2026-09",
            metrics=[
                {"metric_code": "attendance_compliance_rate"},
                {"metric_code": "attendance_compliance_rate"},
            ],
        )


def test_personal_scope_contract_rejects_duplicate_employee_codes():
    from backend.schemas.hr import PersonalPerformanceScopeApplyRequest

    with pytest.raises(ValidationError, match="employees cannot repeat"):
        PersonalPerformanceScopeApplyRequest(
            year_month="2026-09",
            expected_plan_version=1,
            employees=[
                {"employee_code": "EMP001"},
                {"employee_code": "EMP001"},
            ],
        )


def test_personal_entry_contract_requires_one_controlled_input_kind():
    from backend.schemas.hr import PersonalPerformanceEntryApplyRequest

    with pytest.raises(ValidationError, match="exactly one controlled input"):
        PersonalPerformanceEntryApplyRequest(
            year_month="2026-09",
            expected_plan_version=1,
            entries=[
                {
                    "employee_code": "EMP001",
                    "metric_code": "attendance_compliance_rate",
                    "actual_value": 98,
                    "result": "passed",
                }
            ],
        )


def test_personal_entry_contract_requires_both_training_counts_and_unique_keys():
    from backend.schemas.hr import PersonalPerformanceEntryApplyRequest

    with pytest.raises(ValidationError, match="training counts require both values"):
        PersonalPerformanceEntryApplyRequest(
            year_month="2026-09",
            expected_plan_version=1,
            entries=[
                {
                    "employee_code": "EMP001",
                    "metric_code": "training_completion_rate",
                    "completed_count": 4,
                }
            ],
        )

    with pytest.raises(ValidationError, match="employee metric entries cannot repeat"):
        PersonalPerformanceEntryApplyRequest(
            year_month="2026-09",
            expected_plan_version=1,
            entries=[
                {
                    "employee_code": "EMP001",
                    "metric_code": "attendance_compliance_rate",
                    "actual_value": 98,
                },
                {
                    "employee_code": "EMP001",
                    "metric_code": "attendance_compliance_rate",
                    "actual_value": 99,
                },
            ],
        )


def test_personal_scope_contract_carries_the_plan_optimistic_lock_version():
    from backend.schemas.hr import PersonalPerformanceScopeApplyRequest

    request = PersonalPerformanceScopeApplyRequest(
        year_month="2026-09",
        expected_plan_version=2,
        expected_updated_at=datetime(2026, 8, 22, 8, 0, tzinfo=timezone.utc),
        employees=[],
    )

    assert request.expected_plan_version == 2
    assert request.expected_updated_at == datetime(2026, 8, 22, 8, 0, tzinfo=timezone.utc)
