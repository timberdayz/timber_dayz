import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services.hr_income_calculation_service import HRIncomeCalculationService
from modules.core.db import (
    EmployeePerformance,
    EmployeePerformanceInput,
    EmployeeShopAssignment,
    PersonalPerformanceAssignmentSnapshot,
    PersonalPerformanceEmployeeScope,
    PersonalPerformanceEntry,
    PersonalPerformancePlan,
    PerformanceScore,
    SalaryStructure,
)


class _Result:
    def __init__(self, rows=None, scalar=None):
        self.rows = rows or []
        self.scalar = scalar

    def scalars(self):
        return self

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def scalar_one_or_none(self):
        return self.scalar

    def scalar_one(self):
        return self.scalar or False


def test_controlled_personal_score_uses_frozen_target_weight_and_twenty_point_personal_score():
    results = HRIncomeCalculationService.build_controlled_personal_results(
        scopes=[{"employee_code": "EMP001", "is_included": True}],
        assignments_by_employee={
            "EMP001": [
                {"platform_code": "shopee", "shop_id": "A", "sales_target_amount_snapshot": 100},
                {"platform_code": "shopee", "shop_id": "B", "sales_target_amount_snapshot": 50},
            ]
        },
        metrics=[{"metric_code": "attendance"}, {"metric_code": "training"}],
        entry_scores_by_employee={"EMP001": {"attendance": 10, "training": 8}},
        shop_scores={"shopee|a": 70, "shopee|b": 100},
    )

    assert results["EMP001"]["calculation_status"] == "complete"
    assert results["EMP001"]["performance_score"] == 82.0
    assert results["EMP001"]["calculation_details"]["store_base_score"] == 80.0
    assert results["EMP001"]["calculation_details"]["personal_target_score"] == 18


def test_controlled_personal_score_marks_missing_entry_partial_and_excluded_not_participating():
    results = HRIncomeCalculationService.build_controlled_personal_results(
        scopes=[
            {"employee_code": "PARTIAL", "is_included": True},
            {"employee_code": "OUT", "is_included": False},
        ],
        assignments_by_employee={
            "PARTIAL": [{"platform_code": "shopee", "shop_id": "A", "sales_target_amount_snapshot": 100}],
        },
        metrics=[{"metric_code": "attendance"}, {"metric_code": "training"}],
        entry_scores_by_employee={"PARTIAL": {"attendance": 10}},
        shop_scores={"shopee|a": 70},
    )

    assert results["PARTIAL"]["calculation_status"] == "partial"
    assert results["PARTIAL"]["performance_score"] is None
    assert results["OUT"]["calculation_status"] == "not_participating"
    assert results["OUT"]["performance_score"] is None


def test_controlled_personal_result_snapshots_auditable_personal_entries():
    results = HRIncomeCalculationService.build_controlled_personal_results(
        scopes=[{"employee_code": "EMP001", "is_included": True}],
        assignments_by_employee={
            "EMP001": [{"platform_code": "shopee", "shop_id": "A", "sales_target_amount_snapshot": 100}]
        },
        metrics=[
            {
                "metric_code": "attendance",
                "metric_name": "Attendance rate",
                "default_target_value": 100,
                "max_score": 20,
                "guidance": "actual / target",
            }
        ],
        entry_scores_by_employee={"EMP001": {"attendance": 18}},
        entry_details_by_employee={
            "EMP001": {
                "attendance": {
                    "input_payload": {"actual_value": 90},
                    "completion_status": "completed",
                }
            }
        },
        shop_scores={"shopee|a": 80},
    )

    entry = results["EMP001"]["calculation_details"]["personal_target_entries"][0]
    assert entry == {
        "metric_code": "attendance",
        "metric_name": "Attendance rate",
        "metric_direction": None,
        "target_value": 100,
        "input_payload": {"actual_value": 90},
        "max_score": 20,
        "auto_score": 18,
        "formula": "actual / target",
        "completion_status": "completed",
    }


def test_calculate_month_persists_controlled_final_score_for_confirmed_scope():
    added = []
    plan = SimpleNamespace(
        id=1,
        calculation_mode="controlled_targets_v1",
        scope_confirmed_at=object(),
        rule_snapshot={"metrics": [{"metric_code": "attendance"}]},
    )
    scope = SimpleNamespace(id=2, employee_code="EMP001", is_included=True)
    snapshot = SimpleNamespace(
        scope_id=2,
        platform_code="shopee",
        shop_id="A",
        sales_target_amount_snapshot=100,
    )
    entry = SimpleNamespace(scope_id=2, metric_code="attendance", auto_score=18)
    score = SimpleNamespace(
        platform_code="shopee",
        shop_id="A",
        total_score=80,
        score_details={"summary": {"calculation_status": "complete", "formal_ready": True, "ranking_pool": "official"}},
    )

    async def execute(statement, _params=None):
        entity = statement.column_descriptions[0].get("entity") if hasattr(statement, "column_descriptions") else None
        rows_by_entity = {
            PersonalPerformancePlan: _Result(scalar=plan),
            PersonalPerformanceEmployeeScope: _Result(rows=[scope]),
            PersonalPerformanceAssignmentSnapshot: _Result(rows=[snapshot]),
            PersonalPerformanceEntry: _Result(rows=[entry]),
            PerformanceScore: _Result(rows=[score]),
            EmployeeShopAssignment: _Result(rows=[]),
            EmployeePerformanceInput: _Result(rows=[]),
            SalaryStructure: _Result(rows=[]),
            EmployeePerformance: _Result(scalar=None),
        }
        return rows_by_entity.get(entity, _Result(rows=[]))

    db = SimpleNamespace(execute=AsyncMock(side_effect=execute), add=lambda row: added.append(row), commit=AsyncMock())
    result = asyncio.run(HRIncomeCalculationService(db).calculate_month("2026-08"))

    controlled = next(row for row in added if isinstance(row, EmployeePerformance) and row.performance_source_type == "controlled_targets_v1")
    assert controlled.performance_score == 82.0
    assert controlled.calculation_status == "complete"
    assert result["formal_employee_codes"] == ["EMP001"]


def test_controlled_plan_without_confirmed_scope_clears_commission_and_stays_pending():
    added = []
    plan = SimpleNamespace(
        id=1,
        calculation_mode="controlled_targets_v1",
        scope_confirmed_at=None,
        rule_snapshot={"metrics": [{"metric_code": "attendance"}]},
    )
    assignment = SimpleNamespace(
        employee_code="EMP001",
        platform_code="shopee",
        shop_id="A",
        commission_ratio=0.5,
        status="active",
        year_month="2026-08",
    )

    async def execute(statement, _params=None):
        entity = statement.column_descriptions[0].get("entity") if hasattr(statement, "column_descriptions") else None
        rows_by_entity = {
            PersonalPerformancePlan: _Result(scalar=plan),
            PersonalPerformanceEmployeeScope: _Result(rows=[]),
            PersonalPerformanceAssignmentSnapshot: _Result(rows=[]),
            PersonalPerformanceEntry: _Result(rows=[]),
            PerformanceScore: _Result(rows=[]),
            EmployeeShopAssignment: _Result(rows=[assignment]),
            EmployeePerformanceInput: _Result(rows=[]),
            SalaryStructure: _Result(rows=[]),
            EmployeePerformance: _Result(scalar=None),
        }
        return rows_by_entity.get(entity, _Result(rows=[]))

    db = SimpleNamespace(execute=AsyncMock(side_effect=execute), add=lambda row: added.append(row), commit=AsyncMock())
    result = asyncio.run(HRIncomeCalculationService(db).calculate_month("2026-08"))

    pending = next(row for row in added if isinstance(row, EmployeePerformance) and row.performance_source_type == "controlled_targets_v1")
    assert pending.calculation_status == "pending_scope"
    assert pending.performance_score is None
    assert not any(row.__class__.__name__ == "EmployeeCommission" for row in added)
    assert result["formal_employee_codes"] == []
    assert result["commission_allocations"] == []
