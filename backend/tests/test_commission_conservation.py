"""提成**守恒**守护（V2-04）。

背景（ADR-2026-11-21）：提成口径归一后，系统里有三个「总数」：

- **人维度**：某个员工当月总共拿到多少提成（结算预览 / 工资单）；
- **店维度**：某家店当月分出去多少提成（月度结算单 / 店铺维度统计）；
- **员工提成总额**：看板「员工侧分配额」里的提成部分。

这三个数**必须是同一个数**。历史上它们不是 —— 因为同一句公式被独立实现了 4 处，
其中 1 处漏乘系数、1 处少 formal 店铺过滤 ⇒ 同一笔钱在不同页面有不同的数。

现在公式收敛到唯一真源 :mod:`backend.services.commission_caliber`，
本守护用**真实服务方法**（而不是再写一遍公式）验证守恒。

守恒断言：

    Σ(人维度) == Σ(店维度) == Σ(逐店逐人分摊) == 员工提成总额
"""

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services.commission_caliber import calculate_employee_commission
from modules.core.db import (
    EmployeeShopAssignment,
    PerformanceScore,
    ShopCommissionConfig,
    ShopProfitBasis,
)

#: 一组固定输入：两个员工、四家店 —— 含亏损店、未配可分配率的店、跨店员工。
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

#: 舍入容差：分摊到人、汇总到店、汇总到公司各舍入一次，尾差最多几分钱。
TOLERANCE = Decimal("0.05")


class _MockResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def scalars(self):
        return self

    def tuples(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return None


def _assignment_rows():
    rows = []
    for shop_key, shop in INPUTS.items():
        platform_code, shop_id = shop_key.split("|")
        for emp, ratio in shop["employees"].items():
            rows.append(
                SimpleNamespace(
                    employee_code=emp,
                    platform_code=platform_code,
                    shop_id=shop_id,
                    commission_ratio=ratio,
                    role="operator",
                    status="active",
                )
            )
    return rows


def _config_rows():
    return [
        SimpleNamespace(
            year_month="2026-10",
            platform_code=shop_key.split("|")[0],
            shop_id=shop_key.split("|")[1],
            allocatable_profit_rate=shop["allocatable_profit_rate"],
        )
        for shop_key, shop in INPUTS.items()
    ]


def _basis_rows():
    return [
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


def _score_rows():
    return [
        SimpleNamespace(
            period="2026-10",
            platform_code=shop_key.split("|")[0],
            shop_id=shop_key.split("|")[1],
            total_score=80.0,
            rank=1,
            performance_coefficient=0.5,
            score_details={"summary": {"calculation_status": "complete"}},
        )
        for shop_key in INPUTS
    ]


def _make_db():
    db = AsyncMock()

    async def _execute(stmt, params=None):
        if hasattr(stmt, "column_descriptions"):
            entity = stmt.column_descriptions[0].get("entity")
            if entity is EmployeeShopAssignment:
                return _MockResult(rows=_assignment_rows())
            if entity is ShopCommissionConfig:
                return _MockResult(rows=_config_rows())
            if entity is ShopProfitBasis:
                return _MockResult(rows=_basis_rows())
            if entity is PerformanceScore:
                return _MockResult(rows=_score_rows())
        return _MockResult(rows=[])

    db.execute = AsyncMock(side_effect=_execute)
    return db


def _caliber_total():
    """真源算出来的总额（唯一期望值来源）。"""
    total = Decimal("0")
    for shop in INPUTS.values():
        for ratio in shop["employees"].values():
            total += calculate_employee_commission(
                profit_basis_amount=shop["profit_basis_amount"],
                allocatable_profit_rate=shop["allocatable_profit_rate"],
                commission_ratio=ratio,
            )
    return total


def test_employee_dimension_equals_caliber_total():
    """人维度：Σ(员工 expected_commission) == 真源总额。"""
    from backend.services.hr_income_calculation_service import (
        HRIncomeCalculationService,
    )

    service = HRIncomeCalculationService(db=_make_db())
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

    by_employee = sum(
        (Decimal(str(entry["expected_commission"])) for entry in preview["employees"]),
        Decimal("0"),
    )
    assert abs(by_employee - _caliber_total()) <= TOLERANCE


def test_shop_dimension_equals_caliber_total():
    """店维度：Σ(店铺 expected_commission) == 真源总额。"""
    from backend.services.monthly_settlement_service import (
        MonthlySettlementService,
    )

    service = MonthlySettlementService(db=_make_db())
    result = asyncio.run(service.build("2026-10"))

    by_shop = sum(
        (Decimal(str(item["expected_commission"])) for item in result.get("shops", [])),
        Decimal("0"),
    )
    assert abs(by_shop - _caliber_total()) <= TOLERANCE


def test_employee_and_shop_dimensions_are_equal():
    """人维度 == 店维度 —— 这正是 V2-04 要守的那条恒等式。"""
    from backend.services.hr_income_calculation_service import (
        HRIncomeCalculationService,
    )
    from backend.services.monthly_settlement_service import (
        MonthlySettlementService,
    )

    income_service = HRIncomeCalculationService(db=_make_db())
    income_service._load_profit_basis_by_shop = AsyncMock(
        return_value={
            shop_key: {"profit_basis_amount": shop["profit_basis_amount"]}
            for shop_key, shop in INPUTS.items()
        }
    )
    income_service._load_store_performance_by_shop = AsyncMock(
        return_value={
            shop_key: {
                "total_score": 80.0,
                "performance_coefficient": 0.5,
                "sales_target": 1000.0,
            }
            for shop_key in INPUTS
        }
    )
    preview = asyncio.run(income_service.build_settlement_preview("2026-10"))

    settlement_service = MonthlySettlementService(db=_make_db())
    settlement = asyncio.run(settlement_service.build("2026-10"))

    by_employee = sum(
        (Decimal(str(entry["expected_commission"])) for entry in preview["employees"]),
        Decimal("0"),
    )
    by_shop = sum(
        (
            Decimal(str(item["expected_commission"]))
            for item in settlement.get("shops", [])
        ),
        Decimal("0"),
    )

    assert (
        abs(by_employee - by_shop) <= TOLERANCE
    ), f"人维度 {by_employee} != 店维度 {by_shop}"


def test_per_shop_employee_sum_equals_shop_total():
    """逐店口径：该店所有员工的分摊之和 == 该店合计。"""
    from backend.services.monthly_settlement_service import (
        MonthlySettlementService,
    )

    service = MonthlySettlementService(db=_make_db())
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
        assert abs(actual - expected_for_shop) <= TOLERANCE, f"{shop_id} 金额不一致"


def test_loss_shop_does_not_break_conservation():
    """亏损店必须归零，且**不能**把负数带进总额（否则总额会互相抵消）。"""
    from backend.services.monthly_settlement_service import (
        MonthlySettlementService,
    )

    service = MonthlySettlementService(db=_make_db())
    result = asyncio.run(service.build("2026-10"))

    shops = {item["shop_id"]: item for item in result.get("shops", [])}
    assert Decimal(str(shops["s_loss"]["expected_commission"])) == Decimal("0")

    total = sum(
        (Decimal(str(item["expected_commission"])) for item in result.get("shops", [])),
        Decimal("0"),
    )
    assert total >= Decimal("0")
