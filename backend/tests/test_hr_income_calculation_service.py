"""
HRIncomeCalculationService 基础单测
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from modules.core.db import (
    AttendanceRecord,
    EmployeeCommission,
    EmployeePerformance,
    EmployeePerformanceAdjustment,
    EmployeeShopAssignment,
    PerformanceScore,
    ShopCommissionConfig,
    ShopProfitBasis,
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
        return self._mapping_rows or self._rows

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
    service._load_profit_basis_by_shop = AsyncMock(
        return_value={"shopee|s1": {"profit_basis_amount": 1500.0}}
    )
    result = asyncio.run(service.calculate_month("2026-03"))

    assert result["employee_count"] == 1
    assert result["commission_upserts"] == 1
    assert result["performance_upserts"] == 1
    assert any(isinstance(x, EmployeeCommission) for x in added)
    assert any(isinstance(x, EmployeePerformance) for x in added)
    commission = next(x for x in added if isinstance(x, EmployeeCommission))
    assert commission.sales_amount == pytest.approx(1000.0)
    assert commission.commission_amount == pytest.approx(120.0)
    assert commission.commission_rate == pytest.approx(0.12)


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
    service._load_profit_basis_by_shop = AsyncMock(
        return_value={"shopee|s2": {"profit_basis_amount": 900.0}}
    )
    result = asyncio.run(service.calculate_month("2026-01"))

    assert result["employee_count"] == 1
    assert result["commission_upserts"] == 1
    assert result["performance_upserts"] == 1
    assert db.rollback.await_count >= 2


def test_load_profit_basis_by_shop_prefers_shop_profit_basis_snapshot(monkeypatch):
    db = AsyncMock()

    snapshot_row = SimpleNamespace(
        period_month="2026-03",
        platform_code="shopee",
        shop_id="S1",
        profit_basis_amount=1800.0,
    )
    assignment = SimpleNamespace(
        employee_code="E001",
        platform_code="Shopee",
        shop_id="S1",
        commission_ratio=0.1,
        status="active",
        year_month="2026-03",
    )

    async def _execute(stmt, params=None):
        if hasattr(stmt, "column_descriptions"):
            entity = stmt.column_descriptions[0].get("entity")
            if entity is ShopProfitBasis:
                return _MockResult(rows=[snapshot_row])
        return _MockResult(rows=[])

    db.execute = AsyncMock(side_effect=_execute)
    service = HRIncomeCalculationService(db=db)

    async def _unexpected_build(*args, **kwargs):
        raise AssertionError("should not rebuild profit basis when snapshot exists")

    monkeypatch.setattr(
        "backend.services.profit_basis_service.ProfitBasisService.build_profit_basis",
        _unexpected_build,
    )

    result = asyncio.run(service._load_profit_basis_by_shop("2026-03", [assignment]))

    assert result == {"shopee|s1": {"profit_basis_amount": 1800.0}}


def test_calculate_month_employee_performance_uses_store_total_score():
    db = AsyncMock()
    added = []

    assignments = [
        SimpleNamespace(
            employee_code="E100",
            platform_code="Shopee",
            shop_id="S1",
            commission_ratio=0.1,
            status="active",
            year_month="2026-03",
        ),
        SimpleNamespace(
            employee_code="E100",
            platform_code="Shopee",
            shop_id="S2",
            commission_ratio=0.1,
            status="active",
            year_month="2026-03",
        ),
    ]
    cfg_rows = [
        SimpleNamespace(
            year_month="2026-03",
            platform_code="Shopee",
            shop_id="S1",
            allocatable_profit_rate=1.0,
        ),
        SimpleNamespace(
            year_month="2026-03",
            platform_code="Shopee",
            shop_id="S2",
            allocatable_profit_rate=1.0,
        ),
    ]
    perf_rows = [
        SimpleNamespace(
            platform_code="shopee",
            shop_id="S1",
            period="2026-03",
            total_score=92.0,
            score_details={
                "sales": {"target": 900.0},
                "summary": {"status": "complete"},
            },
        ),
        SimpleNamespace(
            platform_code="shopee",
            shop_id="S2",
            period="2026-03",
            total_score=80.0,
            score_details={
                "sales": {"target": 100.0},
                "summary": {"status": "complete"},
            },
        ),
    ]

    async def _execute(stmt, params=None):
        if hasattr(stmt, "column_descriptions"):
            entity = stmt.column_descriptions[0].get("entity")
            if entity is EmployeeShopAssignment:
                return _MockResult(rows=assignments)
            if entity is ShopCommissionConfig:
                return _MockResult(rows=cfg_rows)
            if entity is EmployeeCommission:
                return _MockResult(scalar_value=None)
            if entity is EmployeePerformance:
                return _MockResult(scalar_value=None)
            if entity is PerformanceScore:
                return _MockResult(rows=perf_rows)
        return _MockResult(
            mapping_rows=[
                {
                    "platform_code": "Shopee",
                    "shop_id": "S1",
                    "gmv": 1000.0,
                    "profit": 300.0,
                    "achievement_rate": 60.0,
                },
                {
                    "platform_code": "Shopee",
                    "shop_id": "S2",
                    "gmv": 200.0,
                    "profit": 100.0,
                    "achievement_rate": 50.0,
                },
            ]
        )

    db.execute = AsyncMock(side_effect=_execute)
    db.add = lambda obj: added.append(obj)
    db.commit = AsyncMock()

    service = HRIncomeCalculationService(db=db)
    service._load_profit_basis_by_shop = AsyncMock(
        return_value={
            "shopee|s1": {"profit_basis_amount": 1000.0},
            "shopee|s2": {"profit_basis_amount": 500.0},
        }
    )
    result = asyncio.run(service.calculate_month("2026-03"))

    assert result["employee_count"] == 1
    perf = next(x for x in added if isinstance(x, EmployeePerformance))
    assert perf.actual_sales == pytest.approx(1200.0)
    assert perf.achievement_rate == pytest.approx((60.0 * 1000.0 + 50.0 * 200.0) / 1200.0 / 100.0)
    assert perf.performance_score == pytest.approx(90.8)


def test_calculate_month_employee_performance_applies_attendance_penalties():
    db = AsyncMock()
    added = []

    assignments = [
        SimpleNamespace(
            employee_code="E101",
            platform_code="Shopee",
            shop_id="S1",
            commission_ratio=0.1,
            status="active",
            year_month="2026-03",
        ),
    ]
    cfg_rows = [
        SimpleNamespace(
            year_month="2026-03",
            platform_code="Shopee",
            shop_id="S1",
            allocatable_profit_rate=1.0,
        ),
    ]
    perf_rows = [
        SimpleNamespace(
            platform_code="shopee",
            shop_id="S1",
            period="2026-03",
            total_score=92.0,
            score_details={
                "sales": {"target": 1000.0},
                "summary": {"status": "complete"},
            },
        ),
    ]
    attendance_rows = [
        SimpleNamespace(employee_code="E101", attendance_date="2026-03-01", status="late"),
        SimpleNamespace(employee_code="E101", attendance_date="2026-03-02", status="absent"),
        SimpleNamespace(employee_code="E101", attendance_date="2026-03-03", status="normal"),
    ]

    async def _execute(stmt, params=None):
        if hasattr(stmt, "column_descriptions"):
            entity = stmt.column_descriptions[0].get("entity")
            if entity is EmployeeShopAssignment:
                return _MockResult(rows=assignments)
            if entity is ShopCommissionConfig:
                return _MockResult(rows=cfg_rows)
            if entity is ShopProfitBasis:
                return _MockResult(rows=[])
            if entity is PerformanceScore:
                return _MockResult(rows=perf_rows)
            if entity is AttendanceRecord:
                return _MockResult(rows=attendance_rows)
            if entity is EmployeeCommission:
                return _MockResult(scalar_value=None)
            if entity is EmployeePerformance:
                return _MockResult(scalar_value=None)
        return _MockResult(
            mapping_rows=[
                {
                    "platform_code": "Shopee",
                    "shop_id": "S1",
                    "gmv": 1000.0,
                    "profit": 300.0,
                    "achievement_rate": 60.0,
                }
            ]
        )

    db.execute = AsyncMock(side_effect=_execute)
    db.add = lambda obj: added.append(obj)
    db.commit = AsyncMock()

    service = HRIncomeCalculationService(db=db)
    service._load_profit_basis_by_shop = AsyncMock(
        return_value={"shopee|s1": {"profit_basis_amount": 1000.0}}
    )
    result = asyncio.run(service.calculate_month("2026-03"))

    assert result["employee_count"] == 1
    perf = next(x for x in added if isinstance(x, EmployeePerformance))
    assert perf.performance_score == pytest.approx(86.0)


def test_calculate_month_employee_performance_applies_manual_adjustments():
    db = AsyncMock()
    added = []

    assignments = [
        SimpleNamespace(
            employee_code="E102",
            platform_code="Shopee",
            shop_id="S1",
            commission_ratio=0.1,
            status="active",
            year_month="2026-03",
        ),
    ]
    cfg_rows = [
        SimpleNamespace(
            year_month="2026-03",
            platform_code="Shopee",
            shop_id="S1",
            allocatable_profit_rate=1.0,
        ),
    ]
    perf_rows = [
        SimpleNamespace(
            platform_code="shopee",
            shop_id="S1",
            period="2026-03",
            total_score=92.0,
            score_details={
                "sales": {"target": 1000.0},
                "summary": {"status": "complete"},
            },
        ),
    ]
    adjustment_rows = [
        SimpleNamespace(employee_code="E102", year_month="2026-03", score_delta=3.0, status="active"),
        SimpleNamespace(employee_code="E102", year_month="2026-03", score_delta=-1.5, status="active"),
    ]

    async def _execute(stmt, params=None):
        if hasattr(stmt, "column_descriptions"):
            entity = stmt.column_descriptions[0].get("entity")
            if entity is EmployeeShopAssignment:
                return _MockResult(rows=assignments)
            if entity is ShopCommissionConfig:
                return _MockResult(rows=cfg_rows)
            if entity is ShopProfitBasis:
                return _MockResult(rows=[])
            if entity is PerformanceScore:
                return _MockResult(rows=perf_rows)
            if entity is AttendanceRecord:
                return _MockResult(rows=[])
            if entity is EmployeePerformanceAdjustment:
                return _MockResult(rows=adjustment_rows)
            if entity is EmployeeCommission:
                return _MockResult(scalar_value=None)
            if entity is EmployeePerformance:
                return _MockResult(scalar_value=None)
        return _MockResult(
            mapping_rows=[
                {
                    "platform_code": "Shopee",
                    "shop_id": "S1",
                    "gmv": 1000.0,
                    "profit": 300.0,
                    "achievement_rate": 60.0,
                }
            ]
        )

    db.execute = AsyncMock(side_effect=_execute)
    db.add = lambda obj: added.append(obj)
    db.commit = AsyncMock()

    service = HRIncomeCalculationService(db=db)
    service._load_profit_basis_by_shop = AsyncMock(
        return_value={"shopee|s1": {"profit_basis_amount": 1000.0}}
    )
    result = asyncio.run(service.calculate_month("2026-03"))

    assert result["employee_count"] == 1
    perf = next(x for x in added if isinstance(x, EmployeePerformance))
    assert perf.performance_score == pytest.approx(93.5)
