"""
PayrollGenerationService regression tests
"""

import asyncio
import importlib
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from modules.core.db import (
    EmployeeCommission,
    EmployeePerformance,
    PayrollRecord,
    SalaryStructure,
)


class _MockResult:
    def __init__(self, rows=None, scalar_value=None):
        self._rows = rows or []
        self._scalar_value = scalar_value

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._scalar_value


def _load_service_cls():
    module = importlib.import_module("backend.services.payroll_generation_service")
    return module.PayrollGenerationService


def test_generate_month_creates_draft_payroll_from_salary_commission_and_performance():
    service_cls = _load_service_cls()
    db = AsyncMock()
    added = []

    salary = SimpleNamespace(
        employee_code="EMP001",
        base_salary=Decimal("1000"),
        position_salary=Decimal("500"),
        housing_allowance=Decimal("50"),
        transport_allowance=Decimal("20"),
        meal_allowance=Decimal("10"),
        communication_allowance=Decimal("5"),
        other_allowance=Decimal("15"),
        performance_ratio=0.2,
        status="active",
    )
    commission = SimpleNamespace(
        employee_code="EMP001",
        year_month="2025-01",
        commission_amount=Decimal("300"),
    )
    performance = SimpleNamespace(
        employee_code="EMP001",
        year_month="2025-01",
        performance_score=80.0,
    )

    async def _execute(stmt, params=None):
        if hasattr(stmt, "column_descriptions"):
            entity = stmt.column_descriptions[0].get("entity")
            if entity is SalaryStructure:
                return _MockResult(rows=[salary])
            if entity is EmployeeCommission:
                return _MockResult(rows=[commission])
            if entity is EmployeePerformance:
                return _MockResult(rows=[performance])
            if entity is PayrollRecord:
                return _MockResult(rows=[])
        return _MockResult(rows=[])

    db.execute = AsyncMock(side_effect=_execute)
    db.add = lambda obj: added.append(obj)

    service = service_cls(db=db)
    result = asyncio.run(service.generate_month("2025-01"))

    assert result["payroll_upserts"] == 1
    assert result["locked_conflicts"] == 0
    created = next(x for x in added if isinstance(x, PayrollRecord))
    assert float(created.performance_salary) == 240.0
    assert float(created.allowances) == 100.0
    assert float(created.gross_salary) == 2140.0
    assert float(created.net_salary) == 2140.0
    assert created.status == "draft"


def test_generate_month_preserves_manual_fields_on_existing_draft():
    service_cls = _load_service_cls()
    db = AsyncMock()

    salary = SimpleNamespace(
        employee_code="EMP002",
        base_salary=Decimal("1200"),
        position_salary=Decimal("300"),
        housing_allowance=Decimal("0"),
        transport_allowance=Decimal("0"),
        meal_allowance=Decimal("0"),
        communication_allowance=Decimal("0"),
        other_allowance=Decimal("0"),
        performance_ratio=0.1,
        status="active",
    )
    commission = SimpleNamespace(
        employee_code="EMP002",
        year_month="2025-01",
        commission_amount=Decimal("200"),
    )
    performance = SimpleNamespace(
        employee_code="EMP002",
        year_month="2025-01",
        performance_score=90.0,
    )
    existing = SimpleNamespace(
        id=10,
        employee_code="EMP002",
        year_month="2025-01",
        status="draft",
        overtime_pay=Decimal("50"),
        bonus=Decimal("80"),
        social_insurance_personal=Decimal("10"),
        housing_fund_personal=Decimal("15"),
        income_tax=Decimal("30"),
        other_deductions=Decimal("20"),
        social_insurance_company=Decimal("100"),
        housing_fund_company=Decimal("120"),
    )

    async def _execute(stmt, params=None):
        if hasattr(stmt, "column_descriptions"):
            entity = stmt.column_descriptions[0].get("entity")
            if entity is SalaryStructure:
                return _MockResult(rows=[salary])
            if entity is EmployeeCommission:
                return _MockResult(rows=[commission])
            if entity is EmployeePerformance:
                return _MockResult(rows=[performance])
            if entity is PayrollRecord:
                return _MockResult(rows=[existing])
        return _MockResult(rows=[])

    db.execute = AsyncMock(side_effect=_execute)
    db.add = lambda obj: None

    service = service_cls(db=db)
    result = asyncio.run(service.generate_month("2025-01"))

    assert result["payroll_upserts"] == 1
    assert float(existing.overtime_pay) == 50.0
    assert float(existing.bonus) == 80.0
    assert float(existing.total_deductions) == 75.0
    assert float(existing.performance_salary) == 135.0
    assert float(existing.gross_salary) == 1965.0
    assert float(existing.net_salary) == 1890.0
    assert float(existing.total_cost) == 2185.0


def test_generate_month_reports_locked_conflict_for_confirmed_payroll():
    service_cls = _load_service_cls()
    db = AsyncMock()
    added = []

    salary = SimpleNamespace(
        employee_code="EMP003",
        base_salary=Decimal("1000"),
        position_salary=Decimal("500"),
        housing_allowance=Decimal("0"),
        transport_allowance=Decimal("0"),
        meal_allowance=Decimal("0"),
        communication_allowance=Decimal("0"),
        other_allowance=Decimal("0"),
        performance_ratio=0.2,
        status="active",
    )
    commission = SimpleNamespace(
        employee_code="EMP003",
        year_month="2025-01",
        commission_amount=Decimal("600"),
    )
    performance = SimpleNamespace(
        employee_code="EMP003",
        year_month="2025-01",
        performance_score=100.0,
    )
    existing = SimpleNamespace(
        id=20,
        employee_code="EMP003",
        year_month="2025-01",
        status="confirmed",
        base_salary=Decimal("800"),
        position_salary=Decimal("200"),
        performance_salary=Decimal("0"),
        commission=Decimal("0"),
        allowances=Decimal("0"),
        gross_salary=Decimal("1000"),
        total_deductions=Decimal("0"),
        net_salary=Decimal("1000"),
        overtime_pay=Decimal("0"),
        bonus=Decimal("0"),
        social_insurance_personal=Decimal("0"),
        housing_fund_personal=Decimal("0"),
        income_tax=Decimal("0"),
        other_deductions=Decimal("0"),
        social_insurance_company=Decimal("0"),
        housing_fund_company=Decimal("0"),
    )

    async def _execute(stmt, params=None):
        if hasattr(stmt, "column_descriptions"):
            entity = stmt.column_descriptions[0].get("entity")
            if entity is SalaryStructure:
                return _MockResult(rows=[salary])
            if entity is EmployeeCommission:
                return _MockResult(rows=[commission])
            if entity is EmployeePerformance:
                return _MockResult(rows=[performance])
            if entity is PayrollRecord:
                return _MockResult(rows=[existing])
        return _MockResult(rows=[])

    db.execute = AsyncMock(side_effect=_execute)
    db.add = lambda obj: added.append(obj)

    service = service_cls(db=db)
    result = asyncio.run(service.generate_month("2025-01"))

    assert result["payroll_upserts"] == 0
    assert result["locked_conflicts"] == 1
    assert result["locked_conflict_details"] == [
        {
            "employee_code": "EMP003",
            "year_month": "2025-01",
            "payroll_status": "confirmed",
            "changed_fields": [
                "base_salary",
                "position_salary",
                "performance_salary",
                "commission",
                "gross_salary",
                "net_salary",
                "total_cost",
            ],
            "current_net_salary": 1000.0,
            "recalculated_net_salary": 2400.0,
        }
    ]
    assert added == []
    assert float(existing.net_salary) == 1000.0
