import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.domains.business.routers.hr_employee import _build_employee_income_audit
from modules.core.db import (
    Employee,
    EmployeeCommission,
    EmployeePerformance,
    EmployeePerformanceAdjustment,
    EmployeePerformanceInput,
    EmployeeShopAssignment,
    MonthlyProfitSettlement,
    PayrollRecord,
    PerformanceScore,
    PersonalPerformanceAssignmentSnapshot,
    PersonalPerformanceEmployeeScope,
    PersonalPerformancePlan,
    ShopCommissionConfig,
    ShopProfitBasis,
)


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


def test_controlled_income_audit_reads_confirmed_assignment_snapshot_not_live_assignment():
    employee = SimpleNamespace(employee_code="EMP001", name="Ada")
    plan = SimpleNamespace(id=10, calculation_mode="controlled_targets_v1", scope_confirmed_at=object())
    scope = SimpleNamespace(id=20, employee_code="EMP001", is_included=True)
    frozen = SimpleNamespace(
        scope_id=20, platform_code="shopee", shop_id="FROZEN",
        assignment_ratio_snapshot=0.6, role_snapshot="operator",
        sales_target_amount_snapshot=1000,
    )
    live = SimpleNamespace(platform_code="shopee", shop_id="LIVE", commission_ratio=0.1, role="operator")

    async def execute(statement):
        entity = statement.column_descriptions[0].get("entity")
        rows_by_entity = {
            Employee: _Result(scalar=employee),
            MonthlyProfitSettlement: _Result(scalar=None),
            PersonalPerformancePlan: _Result(scalar=plan),
            PersonalPerformanceEmployeeScope: _Result(scalar=scope),
            PersonalPerformanceAssignmentSnapshot: _Result(rows=[frozen]),
            EmployeeShopAssignment: _Result(rows=[live]),
            ShopCommissionConfig: _Result(scalar=None),
            PerformanceScore: _Result(scalar=None),
            ShopProfitBasis: _Result(scalar=None),
            EmployeePerformanceInput: _Result(rows=[]),
            EmployeePerformanceAdjustment: _Result(rows=[]),
            EmployeePerformance: _Result(scalar=None),
            EmployeeCommission: _Result(scalar=None),
            PayrollRecord: _Result(scalar=None),
        }
        return rows_by_entity[entity]

    payload = asyncio.run(
        _build_employee_income_audit(
            employee_code="EMP001",
            year_month="2026-08",
            db=SimpleNamespace(execute=AsyncMock(side_effect=execute)),
        )
    )

    shop = payload["data"]["shop_assignments"][0]
    assert shop["shop_id"] == "FROZEN"
    assert shop["commission_ratio"] == 0.6
    assert shop["sales_target_amount"] == 1000.0
