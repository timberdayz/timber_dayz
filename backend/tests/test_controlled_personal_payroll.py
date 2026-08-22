from types import SimpleNamespace
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock

from backend.services.payroll_generation_service import PayrollGenerationService
from modules.core.db import (
    Employee,
    EmployeeCommission,
    EmployeePerformance,
    PayrollRecord,
    PersonalPerformanceEmployeeScope,
    PersonalPerformancePlan,
    SalaryStructure,
)


def test_controlled_partial_performance_has_no_performance_salary_coefficient():
    coefficient = PayrollGenerationService._normalize_performance_coefficient(
        SimpleNamespace(
            performance_source_type="controlled_targets_v1",
            calculation_status="partial",
            performance_score=99,
        )
    )

    assert coefficient == 0


class _Result:
    def __init__(self, rows=None, scalar=None):
        self.rows = rows or []
        self.scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return self.rows

    def scalar_one_or_none(self):
        return self.scalar


def test_confirmed_controlled_scope_excludes_outside_employee_from_personal_payroll(monkeypatch):
    import backend.services.payroll_generation_service as module

    plan = SimpleNamespace(id=1, calculation_mode="controlled_targets_v1", scope_confirmed_at=object())
    scope = SimpleNamespace(employee_code="IN_SCOPE", is_included=True)
    salary = SimpleNamespace(
        employee_code="OUT_SCOPE", status="active", effective_date="2026-08-01",
        base_salary=Decimal("1000"), position_salary=0, performance_package_amount=Decimal("100"),
        housing_allowance=0, transport_allowance=0, meal_allowance=0,
        communication_allowance=0, other_allowance=0,
    )
    commission = SimpleNamespace(employee_code="OUT_SCOPE", commission_amount=Decimal("50"))
    stale_performance = SimpleNamespace(
        employee_code="OUT_SCOPE", performance_score=90,
        performance_source_type="shop_inherited", calculation_status="complete",
    )
    added = []

    async def execute(statement):
        entity = statement.column_descriptions[0].get("entity")
        rows_by_entity = {
            PersonalPerformancePlan: _Result(scalar=plan),
            PersonalPerformanceEmployeeScope: _Result(rows=[scope]),
            SalaryStructure: _Result(rows=[salary]),
            EmployeeCommission: _Result(rows=[commission]),
            EmployeePerformance: _Result(rows=[stale_performance]),
            PayrollRecord: _Result(rows=[]),
            Employee: _Result(scalar=SimpleNamespace(status="active", employee_identity_type="employee")),
        }
        return rows_by_entity[entity]

    monkeypatch.setattr(
        module.PerformanceReadinessService,
        "assert_month_performance_ready",
        AsyncMock(),
    )
    db = SimpleNamespace(execute=AsyncMock(side_effect=execute), add=lambda row: added.append(row))

    asyncio.run(PayrollGenerationService(db).generate_month("2026-08"))

    record = next(row for row in added if isinstance(row, PayrollRecord))
    assert record.employee_code == "OUT_SCOPE"
    assert record.performance_salary == 0
    assert record.commission == Decimal("50.00")
