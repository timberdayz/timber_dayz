"""
HRIncomeCalculationService 基础单测
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from modules.core.db import (
    EmployeeCommission,
    EmployeePerformance,
    EmployeeShopAssignment,
    ShopCommissionConfig,
)
from backend.services.hr_income_calculation_service import HRIncomeCalculationService


class _MockResult:
    def __init__(self, rows=None, scalar_value=None, mapping_rows=None):
        self._rows = rows or []
        self._scalar_value = scalar_value
        self._mapping_rows = mapping_rows or []

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def mappings(self):
        return self

    def first(self):
        return self._mapping_rows[0] if self._mapping_rows else None

    def scalar_one_or_none(self):
        return self._scalar_value


def test_calculate_month_no_assignments():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_MockResult(rows=[]))
    service = HRIncomeCalculationService(db=db)

    result = asyncio.run(service.calculate_month("2026-03"))

    assert result["year_month"] == "2026-03"
    assert result["employee_count"] == 0
    assert result["commission_upserts"] == 0
    assert result["performance_upserts"] == 0


def test_calculate_month_upsert_writes():
    db = AsyncMock()
    added = []

    assignment = SimpleNamespace(
        employee_code="E001",
        platform_code="Shopee",
        shop_id="S1",
        commission_ratio=0.1,
        status="active",
        year_month="2026-03",
    )
    cfg = SimpleNamespace(
        year_month="2026-03",
        platform_code="Shopee",
        shop_id="S1",
        allocatable_profit_rate=0.8,
    )

    async def _execute(stmt, params=None):
        if hasattr(stmt, "column_descriptions"):
            entity = stmt.column_descriptions[0].get("entity")
            if entity is EmployeeShopAssignment:
                return _MockResult(rows=[assignment])
            if entity is ShopCommissionConfig:
                return _MockResult(rows=[cfg])
            if entity is EmployeeCommission:
                return _MockResult(scalar_value=None)
            if entity is EmployeePerformance:
                return _MockResult(scalar_value=None)
            return _MockResult(rows=[])
        return _MockResult(
            mapping_rows=[
                {
                    "platform_code": "Shopee",
                    "shop_id": "S1",
                    "gmv": 10000,
                    "profit": 2000,
                    "achievement_rate": 80,
                }
            ]
        )

    db.execute = AsyncMock(side_effect=_execute)
    db.add = lambda obj: added.append(obj)
    db.commit = AsyncMock()

    service = HRIncomeCalculationService(db=db)
    result = asyncio.run(service.calculate_month("2026-03"))

    assert result["employee_count"] == 1
    assert result["commission_upserts"] == 1
    assert result["performance_upserts"] == 1
    assert any(isinstance(x, EmployeeCommission) for x in added)
    assert any(isinstance(x, EmployeePerformance) for x in added)


def test_calculate_month_upsert_fallback_to_cn_sql_when_orm_columns_missing():
    db = AsyncMock()

    assignment = SimpleNamespace(
        employee_code="E002",
        platform_code="Shopee",
        shop_id="S2",
        commission_ratio=0.2,
        status="active",
        year_month="2026-01",
    )
    cfg = SimpleNamespace(
        year_month="2026-01",
        platform_code="Shopee",
        shop_id="S2",
        allocatable_profit_rate=1.0,
    )

    async def _execute(stmt, params=None):
        if hasattr(stmt, "column_descriptions"):
            entity = stmt.column_descriptions[0].get("entity")
            if entity is EmployeeShopAssignment:
                return _MockResult(rows=[assignment])
            if entity is ShopCommissionConfig:
                return _MockResult(rows=[cfg])
            if entity is EmployeeCommission:
                raise Exception("column employee_commissions.employee_code does not exist")
            if entity is EmployeePerformance:
                raise Exception("column employee_performance.employee_code does not exist")
            return _MockResult(rows=[])
        sql = str(stmt)
        if "FROM api.business_overview_shop_racing_module" in sql:
            return _MockResult(
                mapping_rows=[
                    {
                        "platform_code": "Shopee",
                        "shop_id": "S2",
                        "gmv": 5000,
                        "profit": 1000,
                        "achievement_rate": 70,
                    }
                ]
            )
        if "update c_class.employee_commissions" in sql:
            return SimpleNamespace(rowcount=0)
        if "update c_class.employee_performance" in sql:
            return SimpleNamespace(rowcount=0)
        return _MockResult(rows=[])

    db.execute = AsyncMock(side_effect=_execute)
    db.add = lambda obj: None
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    service = HRIncomeCalculationService(db=db)
    result = asyncio.run(service.calculate_month("2026-01"))

    assert result["employee_count"] == 1
    assert result["commission_upserts"] == 1
    assert result["performance_upserts"] == 1
    assert db.rollback.await_count >= 2
