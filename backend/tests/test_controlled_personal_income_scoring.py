import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services.hr_income_calculation_service import HRIncomeCalculationService
from modules.core.db import (
    EmployeeCommission,
    EmployeePerformance,
    EmployeePerformanceInput,
    EmployeeShopAssignment,
    PayrollRecord,
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


def test_controlled_partial_result_clears_draft_payroll_variable_income():
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
    score = SimpleNamespace(
        platform_code="shopee",
        shop_id="A",
        total_score=80,
        score_details={"summary": {"calculation_status": "complete", "formal_ready": True, "ranking_pool": "official"}},
    )
    payroll = SimpleNamespace(
        employee_code="EMP001", year_month="2026-08", status="draft",
        base_salary=1000, position_salary=200, performance_salary=300, commission=400,
        overtime_pay=0, allowances=0, bonus=0, social_insurance_personal=0,
        housing_fund_personal=0, income_tax=0, other_deductions=0,
        social_insurance_company=0, housing_fund_company=0,
        gross_salary=1900, total_deductions=0, net_salary=1900, total_cost=1900,
    )

    async def execute(statement, _params=None):
        entity = statement.column_descriptions[0].get("entity") if hasattr(statement, "column_descriptions") else None
        rows_by_entity = {
            PersonalPerformancePlan: _Result(scalar=plan),
            PersonalPerformanceEmployeeScope: _Result(rows=[scope]),
            PersonalPerformanceAssignmentSnapshot: _Result(rows=[snapshot]),
            PersonalPerformanceEntry: _Result(rows=[]),
            PerformanceScore: _Result(rows=[score]),
            EmployeeShopAssignment: _Result(rows=[]),
            EmployeePerformanceInput: _Result(rows=[]),
            SalaryStructure: _Result(rows=[]),
            PayrollRecord: _Result(rows=[payroll]),
            EmployeePerformance: _Result(scalar=None),
        }
        return rows_by_entity.get(entity, _Result(rows=[]))

    db = SimpleNamespace(execute=AsyncMock(side_effect=execute), add=lambda row: added.append(row), commit=AsyncMock())
    asyncio.run(HRIncomeCalculationService(db).calculate_month("2026-08"))

    assert payroll.base_salary == 1000
    assert payroll.position_salary == 200
    assert payroll.performance_salary == 0
    assert payroll.commission == 0
    assert payroll.gross_salary == 1200
    assert payroll.net_salary == 1200


def test_confirmed_controlled_scope_never_falls_back_to_post_confirmation_assignment():
    added = []
    plan = SimpleNamespace(
        id=1,
        calculation_mode="controlled_targets_v1",
        scope_confirmed_at=object(),
        rule_snapshot={"metrics": [{"metric_code": "attendance"}]},
    )
    scope = SimpleNamespace(id=2, employee_code="IN_SCOPE", is_included=True)
    snapshot = SimpleNamespace(
        scope_id=2,
        platform_code="shopee",
        shop_id="A",
        sales_target_amount_snapshot=100,
    )
    entry = SimpleNamespace(scope_id=2, metric_code="attendance", auto_score=20)
    score = SimpleNamespace(
        platform_code="shopee",
        shop_id="A",
        total_score=80,
        score_details={"summary": {"calculation_status": "complete", "formal_ready": True, "ranking_pool": "official"}},
    )
    post_confirmation_assignment = SimpleNamespace(
        employee_code="OUT_SCOPE", platform_code="shopee", shop_id="A",
        commission_ratio=0, status="active", year_month="2026-08",
    )

    async def execute(statement, _params=None):
        entity = statement.column_descriptions[0].get("entity") if hasattr(statement, "column_descriptions") else None
        rows_by_entity = {
            PersonalPerformancePlan: _Result(scalar=plan),
            PersonalPerformanceEmployeeScope: _Result(rows=[scope]),
            PersonalPerformanceAssignmentSnapshot: _Result(rows=[snapshot]),
            PersonalPerformanceEntry: _Result(rows=[entry]),
            PerformanceScore: _Result(rows=[score]),
            EmployeeShopAssignment: _Result(rows=[post_confirmation_assignment]),
            EmployeePerformanceInput: _Result(rows=[]),
            SalaryStructure: _Result(rows=[]),
            EmployeePerformance: _Result(scalar=None),
        }
        return rows_by_entity.get(entity, _Result(rows=[]))

    db = SimpleNamespace(execute=AsyncMock(side_effect=execute), add=lambda row: added.append(row), commit=AsyncMock())
    result = asyncio.run(HRIncomeCalculationService(db).calculate_month("2026-08"))

    scores = [row for row in added if isinstance(row, EmployeePerformance)]
    assert [row.employee_code for row in scores] == ["IN_SCOPE"]
    assert result["formal_employee_codes"] == ["IN_SCOPE"]


def test_not_participating_employee_keeps_recalculated_independent_commission_in_draft_payroll():
    added = []
    plan = SimpleNamespace(
        id=1,
        calculation_mode="controlled_targets_v1",
        scope_confirmed_at=object(),
        rule_snapshot={"metrics": [{"metric_code": "attendance"}]},
    )
    scope = SimpleNamespace(id=2, employee_code="OUT", is_included=False)
    assignment = SimpleNamespace(
        employee_code="OUT", platform_code="shopee", shop_id="A",
        commission_ratio=0.5, status="active", year_month="2026-08",
    )
    score = SimpleNamespace(
        platform_code="shopee", shop_id="A", total_score=80,
        performance_coefficient=1,
        score_details={"summary": {"calculation_status": "complete", "formal_ready": True, "ranking_pool": "official"}},
    )
    payroll = SimpleNamespace(
        employee_code="OUT", year_month="2026-08", status="draft",
        base_salary=1000, position_salary=0, performance_salary=300, commission=400,
        overtime_pay=0, allowances=0, bonus=0, social_insurance_personal=0,
        housing_fund_personal=0, income_tax=0, other_deductions=0,
        social_insurance_company=0, housing_fund_company=0,
        gross_salary=1700, total_deductions=0, net_salary=1700, total_cost=1700,
    )

    async def execute(statement, _params=None):
        entity = statement.column_descriptions[0].get("entity") if hasattr(statement, "column_descriptions") else None
        rows_by_entity = {
            PersonalPerformancePlan: _Result(scalar=plan),
            PersonalPerformanceEmployeeScope: _Result(rows=[scope]),
            PersonalPerformanceAssignmentSnapshot: _Result(rows=[]),
            PersonalPerformanceEntry: _Result(rows=[]),
            PerformanceScore: _Result(rows=[score]),
            EmployeeShopAssignment: _Result(rows=[assignment]),
            EmployeePerformanceInput: _Result(rows=[]),
            SalaryStructure: _Result(rows=[]),
            PayrollRecord: _Result(rows=[payroll]),
            EmployeePerformance: _Result(scalar=None),
            EmployeeCommission: _Result(scalar=None),
        }
        return rows_by_entity.get(entity, _Result(rows=[]))

    db = SimpleNamespace(execute=AsyncMock(side_effect=execute), add=lambda row: added.append(row), commit=AsyncMock())
    service = HRIncomeCalculationService(db)
    service._load_shop_metrics = AsyncMock(return_value={"shopee|a": {"monthly_sales": 100, "achievement_rate": 1}})
    service._load_profit_basis_by_shop = AsyncMock(return_value={"shopee|a": {"profit_basis_amount": 100}})
    service._load_store_performance_by_shop = AsyncMock(return_value={"shopee|a": {"performance_coefficient": 1, "total_score": 80, "sales_target": 100}})

    asyncio.run(service.calculate_month("2026-08"))

    assert payroll.performance_salary == 0
    assert payroll.commission == 50
    assert payroll.gross_salary == 1050


def test_confirmed_scope_keeps_in_scope_sales_aggregate_without_writing_outside_employee():
    added = []
    plan = SimpleNamespace(
        id=1,
        calculation_mode="controlled_targets_v1",
        scope_confirmed_at=object(),
        rule_snapshot={"metrics": [{"metric_code": "attendance"}]},
    )
    scope = SimpleNamespace(id=2, employee_code="IN_SCOPE", is_included=True)
    snapshot = SimpleNamespace(
        scope_id=2, platform_code="shopee", shop_id="A", sales_target_amount_snapshot=100
    )
    entry = SimpleNamespace(scope_id=2, metric_code="attendance", auto_score=20)
    score = SimpleNamespace(
        platform_code="shopee", shop_id="A", total_score=80,
        score_details={"summary": {"calculation_status": "complete", "formal_ready": True, "ranking_pool": "official"}},
    )
    assignments = [
        SimpleNamespace(employee_code="IN_SCOPE", platform_code="shopee", shop_id="A", commission_ratio=0, status="active", year_month="2026-08"),
        SimpleNamespace(employee_code="OUT_SCOPE", platform_code="shopee", shop_id="A", commission_ratio=0, status="active", year_month="2026-08"),
    ]

    async def execute(statement, _params=None):
        entity = statement.column_descriptions[0].get("entity") if hasattr(statement, "column_descriptions") else None
        rows_by_entity = {
            PersonalPerformancePlan: _Result(scalar=plan),
            PersonalPerformanceEmployeeScope: _Result(rows=[scope]),
            PersonalPerformanceAssignmentSnapshot: _Result(rows=[snapshot]),
            PersonalPerformanceEntry: _Result(rows=[entry]),
            PerformanceScore: _Result(rows=[score]),
            EmployeeShopAssignment: _Result(rows=assignments),
            EmployeePerformanceInput: _Result(rows=[]),
            SalaryStructure: _Result(rows=[]),
            EmployeePerformance: _Result(scalar=None),
        }
        return rows_by_entity.get(entity, _Result(rows=[]))

    db = SimpleNamespace(execute=AsyncMock(side_effect=execute), add=lambda row: added.append(row), commit=AsyncMock())
    service = HRIncomeCalculationService(db)
    service._load_shop_metrics = AsyncMock(return_value={"shopee|a": {"monthly_sales": 120, "achievement_rate": 0.75}})
    service._load_profit_basis_by_shop = AsyncMock(return_value={})
    service._load_store_performance_by_shop = AsyncMock(return_value={"shopee|a": {"performance_coefficient": 1, "total_score": 80, "sales_target": 100}})

    asyncio.run(service.calculate_month("2026-08"))

    results = [row for row in added if isinstance(row, EmployeePerformance)]
    assert [row.employee_code for row in results] == ["IN_SCOPE"]
    assert results[0].actual_sales == 120
    assert results[0].achievement_rate == 0.75
