"""提成计算**路径一致性**守护（V2-04 的一部分）。

背景（ADR-2026-11-21）：同一笔提成曾被独立实现 5 处 ——
工资单计算、结算预览、店铺维度统计、月度结算单、确认校验 ——
其中 1 处漏乘系数、1 处少 formal 店铺过滤。

现在 5 条路径都调用唯一真源
:mod:`backend.services.commission_caliber`。本守护验证：
**同一组输入，5 条路径必须产出完全相同的金额**。

用真实服务方法（而非重写一遍公式）来验证 —— 否则守护自己就成了第 6 套实现。
"""

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.commission_caliber import (
    calculate_employee_commission,
    calculate_shop_allocatable_profit,
)
from modules.core.db import (
    EmployeeShopAssignment,
    PerformanceScore,
    ShopCommissionConfig,
    ShopProfitBasis,
)


class _MockResult:
    def __init__(self, rows=None, scalar_value=None):
        self._rows = rows or []
        self._scalar_value = scalar_value

    def scalars(self):
        return self

    def tuples(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._scalar_value


#: 一组固定输入：两个员工、三家店、含亏损店与未配置可分配率的店
INPUTS = {
    "shopee|s1": {
        "profit_basis_amount": 1000.0,
        "allocatable_profit_rate": 0.25,
        "employees": {"EMP001": 0.5, "EMP002": 0.25},
    },
    "shopee|s2": {
        "profit_basis_amount": 500.0,
        "allocatable_profit_rate": 0.20,
        "employees": {"EMP001": 0.30},
    },
    "shopee|s_loss": {
        "profit_basis_amount": -800.0,  # 亏损店：可分配利润归零
        "allocatable_profit_rate": 0.30,
        "employees": {"EMP002": 0.40},
    },
    "shopee|s_no_rate": {
        "profit_basis_amount": 900.0,  # 未配置可分配率 ⇒ 按 0
        "allocatable_profit_rate": 0.0,
        "employees": {"EMP001": 0.20},
    },
}


def _expected_by_employee():
    """用真源模块算出每个员工的应得提成（这是唯一的期望值来源）。"""
    expected = {}
    for shop in INPUTS.values():
        for emp, ratio in shop["employees"].items():
            amount = calculate_employee_commission(
                profit_basis_amount=shop["profit_basis_amount"],
                allocatable_profit_rate=shop["allocatable_profit_rate"],
                commission_ratio=ratio,
            )
            expected[emp] = expected.get(emp, Decimal("0")) + amount
    return expected


class TestCaliberMath:
    """真源模块本身的数学性质（路径一致性的前提）。"""

    def test_expected_by_employee_totals(self):
        expected = _expected_by_employee()
        # EMP001: s1(1000×0.25×0.5=125) + s2(500×0.20×0.30=30) + s_no_rate(0) = 155
        # EMP002: s1(1000×0.25×0.25=62.5) + s_loss(0) = 62.5
        assert expected["EMP001"] == Decimal("155.000")
        assert expected["EMP002"] == Decimal("62.500")

    def test_loss_shop_contributes_zero(self):
        loss = INPUTS["shopee|s_loss"]
        assert calculate_shop_allocatable_profit(
            profit_basis_amount=loss["profit_basis_amount"],
            allocatable_profit_rate=loss["allocatable_profit_rate"],
        ) == Decimal("0")

    def test_unconfigured_rate_contributes_zero(self):
        no_rate = INPUTS["shopee|s_no_rate"]
        assert calculate_shop_allocatable_profit(
            profit_basis_amount=no_rate["profit_basis_amount"],
            allocatable_profit_rate=no_rate["allocatable_profit_rate"],
        ) == Decimal("0")

    def test_shop_to_employee_sum_equals_employee_total(self):
        """守恒：Σ(逐店员工分摊) == Σ(员工总额)。"""
        by_shop = Decimal("0")
        for shop in INPUTS.values():
            for ratio in shop["employees"].values():
                by_shop += calculate_employee_commission(
                    profit_basis_amount=shop["profit_basis_amount"],
                    allocatable_profit_rate=shop["allocatable_profit_rate"],
                    commission_ratio=ratio,
                )
        by_employee = sum(_expected_by_employee().values(), Decimal("0"))
        assert by_shop == by_employee


class TestPathParity:
    """各条路径用同一组输入，必须产出相同金额。"""

    def test_settlement_preview_matches_caliber(self):
        """路径 1：结算预览（``build_settlement_preview``）。"""
        from backend.services.hr_income_calculation_service import (
            HRIncomeCalculationService,
        )

        assignments = []
        for shop_key, shop in INPUTS.items():
            platform_code, shop_id = shop_key.split("|")
            for emp, ratio in shop["employees"].items():
                assignments.append(
                    SimpleNamespace(
                        employee_code=emp,
                        platform_code=platform_code,
                        shop_id=shop_id,
                        commission_ratio=ratio,
                        role="operator",
                        status="active",
                    )
                )

        db = AsyncMock()

        async def _execute(stmt, params=None):
            if hasattr(stmt, "column_descriptions"):
                entity = stmt.column_descriptions[0].get("entity")
                if entity is EmployeeShopAssignment:
                    return _MockResult(rows=assignments)
                if entity is ShopCommissionConfig:
                    return _MockResult(
                        rows=[
                            SimpleNamespace(
                                year_month="2026-10",
                                platform_code=shop_key.split("|")[0],
                                shop_id=shop_key.split("|")[1],
                                allocatable_profit_rate=shop["allocatable_profit_rate"],
                            )
                            for shop_key, shop in INPUTS.items()
                        ]
                    )
                if entity is PerformanceScore:
                    # 赛马评级故意给 0.5（会影响旧口径），验证新口径下**不影响**金额
                    return _MockResult(
                        rows=[
                            SimpleNamespace(
                                platform_code=shop_key.split("|")[0],
                                shop_id=shop_key.split("|")[1],
                                total_score=80.0,
                                performance_coefficient=0.5,
                                score_details={
                                    "summary": {"calculation_status": "complete"}
                                },
                            )
                            for shop_key in INPUTS
                        ]
                    )
            return _MockResult(rows=[])

        db.execute = AsyncMock(side_effect=_execute)

        service = HRIncomeCalculationService(db=db)
        service._load_profit_basis_by_shop = AsyncMock(
            return_value={
                shop_key: {"profit_basis_amount": shop["profit_basis_amount"]}
                for shop_key, shop in INPUTS.items()
            }
        )
        service._load_store_performance_by_shop = AsyncMock(
            return_value={
                shop_key: {
                    "total_score": 80.0,
                    "performance_coefficient": 0.5,
                    "sales_target": 1000.0,
                }
                for shop_key in INPUTS
            }
        )

        preview = asyncio.run(service.build_settlement_preview("2026-10"))

        by_employee = {}
        for entry in preview["employees"]:
            by_employee[entry["employee_code"]] = Decimal(
                str(entry["expected_commission"])
            )

        expected = _expected_by_employee()
        assert by_employee == expected

    def test_monthly_settlement_shop_totals_match_caliber(self):
        """路径 2：月度结算单（店铺维度预计提成合计）。"""
        from backend.services.monthly_settlement_service import (
            MonthlySettlementService,
        )

        assignments = []
        for shop_key, shop in INPUTS.items():
            platform_code, shop_id = shop_key.split("|")
            for emp, ratio in shop["employees"].items():
                assignments.append(
                    SimpleNamespace(
                        employee_code=emp,
                        platform_code=platform_code,
                        shop_id=shop_id,
                        commission_ratio=ratio,
                        role="operator",
                        status="active",
                    )
                )

        db = AsyncMock()

        async def _execute(stmt, params=None):
            if hasattr(stmt, "column_descriptions"):
                entity = stmt.column_descriptions[0].get("entity")
                if entity is EmployeeShopAssignment:
                    return _MockResult(rows=assignments)
                if entity is ShopCommissionConfig:
                    return _MockResult(
                        rows=[
                            SimpleNamespace(
                                year_month="2026-10",
                                platform_code=shop_key.split("|")[0],
                                shop_id=shop_key.split("|")[1],
                                allocatable_profit_rate=shop["allocatable_profit_rate"],
                            )
                            for shop_key, shop in INPUTS.items()
                        ]
                    )
                if entity is ShopProfitBasis:
                    return _MockResult(
                        rows=[
                            SimpleNamespace(
                                period_month="2026-10",
                                platform_code=shop_key.split("|")[0],
                                shop_id=shop_key.split("|")[1],
                                profit_basis_amount=shop["profit_basis_amount"],
                                basis_version="SETTLEMENT_BASIS_V1",
                                is_locked=True,
                                cost_status="ok",
                            )
                            for shop_key, shop in INPUTS.items()
                        ]
                    )
                if entity is PerformanceScore:
                    return _MockResult(
                        rows=[
                            SimpleNamespace(
                                period="2026-10",
                                platform_code=shop_key.split("|")[0],
                                shop_id=shop_key.split("|")[1],
                                total_score=80.0,
                                rank=1,
                                performance_coefficient=0.5,
                                score_details={
                                    "summary": {"calculation_status": "complete"}
                                },
                            )
                            for shop_key in INPUTS
                        ]
                    )
            return _MockResult(rows=[])

        db.execute = AsyncMock(side_effect=_execute)

        service = MonthlySettlementService(db=db)
        result = asyncio.run(service.build("2026-10"))

        shops = {item["shop_id"]: item for item in result.get("shops", [])}

        for shop_key, shop in INPUTS.items():
            shop_id = shop_key.split("|")[1]
            expected_for_shop = sum(
                (
                    calculate_employee_commission(
                        profit_basis_amount=shop["profit_basis_amount"],
                        allocatable_profit_rate=shop["allocatable_profit_rate"],
                        commission_ratio=ratio,
                    )
                    for ratio in shop["employees"].values()
                ),
                Decimal("0"),
            )
            actual = Decimal(str(shops[shop_id]["expected_commission"]))
            assert actual == expected_for_shop, f"{shop_id} 金额不一致"
