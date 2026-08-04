from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.labor_cost_projection_service import LaborCostProjectionService
from modules.core.db import EmployeeLaborCostAllocation, EmployeeShopAssignment, PayrollRecord


def _assignment(platform_code: str, shop_id: str, employee_code: str = "EMP001"):
    return SimpleNamespace(
        employee_code=employee_code,
        platform_code=platform_code,
        shop_id=shop_id,
        status="active",
    )


def _payroll(**overrides):
    payload = {
        "employee_code": "EMP001",
        "base_salary": Decimal("3000"),
        "position_salary": Decimal("1000"),
        "allowances": Decimal("300"),
        "overtime_pay": Decimal("200"),
        "bonus": Decimal("100"),
        "social_insurance_company": Decimal("400"),
        "housing_fund_company": Decimal("0"),
        "performance_salary": Decimal("600"),
        "commission": Decimal("400"),
        "status": "draft",
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_build_rows_evenly_splits_pre_commission_and_performance_but_keeps_commission_at_source_shop():
    rows = LaborCostProjectionService.build_allocation_rows(
        payroll=_payroll(),
        assignments=[
            _assignment("shopee", "shop-1"),
            _assignment("shopee", "shop-2"),
        ],
        commission_by_shop={
            ("shopee", "shop-1"): Decimal("150"),
            ("shopee", "shop-2"): Decimal("250"),
        },
    )

    assert [row["allocation_scope"] for row in rows] == ["shop", "shop"]
    assert [row["pre_commission_amount"] for row in rows] == [Decimal("2500.00"), Decimal("2500.00")]
    assert [row["performance_amount"] for row in rows] == [Decimal("300.00"), Decimal("300.00")]
    assert [row["commission_amount"] for row in rows] == [Decimal("150.00"), Decimal("250.00")]
    assert [row["total_amount"] for row in rows] == [Decimal("2950.00"), Decimal("3050.00")]


def test_build_rows_sends_unassigned_employee_cost_to_company_scope():
    rows = LaborCostProjectionService.build_allocation_rows(
        payroll=_payroll(employee_code="ADM001", commission=Decimal("0")),
        assignments=[],
        commission_by_shop={},
    )

    assert rows == [
        {
            "employee_code": "ADM001",
            "platform_code": None,
            "shop_id": None,
            "allocation_scope": "company",
            "allocation_ratio": Decimal("1.000000"),
            "pre_commission_amount": Decimal("5000.00"),
            "performance_amount": Decimal("600.00"),
            "commission_amount": Decimal("0.00"),
            "total_amount": Decimal("5600.00"),
            "source_payroll_status": "draft",
        }
    ]


class _ScalarsResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


@pytest.mark.asyncio
async def test_refresh_month_persists_projected_rows_for_each_active_shop():
    db = AsyncMock()
    added = []
    payroll = _payroll()

    async def execute(stmt, *_args, **_kwargs):
        entity = stmt.column_descriptions[0].get("entity")
        if entity is PayrollRecord:
            return _ScalarsResult([payroll])
        if entity is EmployeeShopAssignment:
            return _ScalarsResult([
                _assignment("shopee", "shop-1"),
                _assignment("shopee", "shop-2"),
            ])
        if entity is EmployeeLaborCostAllocation:
            return _ScalarsResult([])
        raise AssertionError(f"unexpected entity: {entity}")

    db.execute = AsyncMock(side_effect=execute)
    db.add = added.append
    service = LaborCostProjectionService(db)

    result = await service.refresh_month(
        "2026-09",
        commission_by_employee_shop={
            "EMP001": {
                ("shopee", "shop-1"): Decimal("150"),
                ("shopee", "shop-2"): Decimal("250"),
            }
        },
    )

    assert result == {"year_month": "2026-09", "allocation_upserts": 2}
    assert len(added) == 2
    assert [record.pre_commission_amount for record in added] == [Decimal("2500.00"), Decimal("2500.00")]
    assert [record.performance_amount for record in added] == [Decimal("300.00"), Decimal("300.00")]
    assert [record.commission_amount for record in added] == [Decimal("150.00"), Decimal("250.00")]
    assert [record.calculation_status for record in added] == ["projected", "projected"]
    db.commit.assert_awaited_once()
