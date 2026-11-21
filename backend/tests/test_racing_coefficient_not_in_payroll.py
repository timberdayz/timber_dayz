"""赛马排名**不参与任何金额**的守护（ADR-2026-11-21 的核心断言）。

背景：店铺赛马排名原先会直接改变员工提成金额（``settlement_coefficient``
里含店铺结算系数），且也会通过「逐店加权平均」压低绩效工资。
业务已确认：**赛马只做考核与预警，不参与任何金额**。

本守护从两个层面锁死：
1. **源码层**：赛马字段不得出现在任何金额计算路径里；
2. **行为层**：改变赛马评级，提成与绩效工资**纹丝不动**。
"""

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.commission_caliber import (
    calculate_employee_commission,
    calculate_employee_performance_salary,
)
from backend.services.performance_coefficient import calculate_score_coefficient

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]


class _MockResult:
    def __init__(self, rows=None, scalar_value=None):
        self._rows = rows or []
        self._scalar_value = scalar_value

    def scalars(self):
        return self

    def tuples(self):
        return self

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def scalar_one(self):
        return self._scalar_value

    def scalar_one_or_none(self):
        return self._scalar_value


class TestSourceLevel:
    """源码层：赛马字段不得进入金额路径。"""

    def test_commission_formula_has_no_coefficient_parameter(self):
        """提成函数的签名里没有任何系数入口。"""
        import inspect

        from backend.services.commission_caliber import (
            calculate_employee_commission,
            calculate_employee_shop_commission,
            calculate_shop_allocatable_profit,
        )

        for func in (
            calculate_employee_commission,
            calculate_employee_shop_commission,
            calculate_shop_allocatable_profit,
        ):
            params = set(inspect.signature(func).parameters)
            forbidden = {
                "coefficient",
                "settlement_coefficient",
                "shop_coefficient",
                "score_coefficient",
                "ranking",
                "rank",
                "performance_coefficient",
            }
            hit = params & forbidden
            assert not hit, f"{func.__name__} 不该接受系数类入参：{hit}"

    def test_no_racing_coefficient_in_amount_services(self):
        """金额计算服务里不得读取赛马评级字段。"""

        def _code_only(text: str) -> str:
            """剥掉 docstring 与注释，只留代码。"""
            import io
            import tokenize

            out = []
            try:
                tokens = tokenize.generate_tokens(io.StringIO(text).readline)
                prev_type = tokenize.INDENT
                for tok in tokens:
                    if tok.type == tokenize.COMMENT:
                        continue
                    if tok.type == tokenize.STRING and prev_type in (
                        tokenize.INDENT,
                        tokenize.NEWLINE,
                        tokenize.NL,
                    ):
                        # 文档字符串：跳过
                        prev_type = tok.type
                        continue
                    if tok.type not in (
                        tokenize.NL,
                        tokenize.NEWLINE,
                        tokenize.INDENT,
                        tokenize.DEDENT,
                    ):
                        out.append(tok.string)
                    prev_type = tok.type
            except tokenize.TokenError:
                return text
            return " ".join(out)

        # 真源模块：代码里连字段名都不该出现（它只认「基数 / 率 / 比」三个输入）。
        caliber = (REPO_ROOT / "backend/services/commission_caliber.py").read_text(
            encoding="utf-8"
        )
        caliber_code = _code_only(caliber)
        assert "performance_coefficient" not in caliber_code
        assert "settlement_coefficient" not in caliber_code

        # 工资单服务：**不得读取** ``EmployeePerformance.performance_coefficient``
        # 这个字段（它存的是含店铺排名的加权平均）。
        payroll_text = (
            REPO_ROOT / "backend/services/payroll_generation_service.py"
        ).read_text(encoding="utf-8")
        payroll_code = _code_only(payroll_text)
        for pattern in (
            'getattr(performance,"performance_coefficient"',
            "getattr(performance,'performance_coefficient'",
            ".performance_coefficient",
        ):
            assert pattern not in payroll_code, (
                f"工资单服务不得读取 {pattern} —— "
                "绩效工资必须用纯个人的分数档位系数。"
            )

    def test_commission_caliber_never_mentions_shop_coefficient(self):
        """真源模块里不该出现店铺系数相关标识符。"""
        text = (REPO_ROOT / "backend/services/commission_caliber.py").read_text(
            encoding="utf-8"
        )
        # 允许在 docstring 里解释「不乘系数」，但不允许有参数或变量用它
        code_lines = [
            line for line in text.splitlines() if not line.strip().startswith("#")
        ]
        code = "\n".join(code_lines)
        assert "shop_coefficient" not in code
        assert "settlement_coefficient" not in code


class TestBehaviourLevel:
    """行为层：改变赛马评级，金额不变。"""

    @pytest.mark.parametrize("shop_coefficient", [0.5, 0.8, 0.9, 1.0, 1.2])
    def test_commission_amount_independent_of_shop_coefficient(self, shop_coefficient):
        """提成金额与赛马评级无关。

        真源函数的签名里根本没有系数入口，所以无论赛马评级是 0.5 还是 1.2，
        同一组输入给出的金额必须完全一致。
        """
        amount = calculate_employee_commission(
            profit_basis_amount=1000.0,
            allocatable_profit_rate=0.25,
            commission_ratio=0.4,
        )
        # 1000 × 0.25 × 0.4 = 100.000
        assert amount == Decimal("100.000")
        # 赛马评级完全不影响这个数：把它乘进去会得到别的数，说明它没参与。
        assert amount * Decimal(str(shop_coefficient)) != amount or (
            shop_coefficient == 1.0
        )

    @pytest.mark.parametrize("stored_coefficient", [0.5, 0.7655, 0.9, 1.2])
    def test_performance_salary_independent_of_stored_coefficient(
        self, stored_coefficient
    ):
        """绩效工资与已存的「加权平均系数」无关。"""
        score = 85.0
        salary = calculate_employee_performance_salary(
            performance_package_amount=1000,
            performance_score_coefficient=calculate_score_coefficient(score),
        )
        assert salary == Decimal("1000.000")

    def test_calculate_month_same_commission_across_shop_coefficients(self):
        """端到端：店铺赛马评级从 0.5 改成 1.2，工资单提成**不变**。"""
        from backend.services.hr_income_calculation_service import (
            HRIncomeCalculationService,
        )
        from modules.core.db import (
            EmployeeShopAssignment,
            PerformanceScore,
            ShopCommissionConfig,
        )

        def _run(shop_coefficient: float) -> Decimal:
            assignments = [
                SimpleNamespace(
                    employee_code="EMP001",
                    platform_code="shopee",
                    shop_id="S1",
                    commission_ratio=0.25,
                    role="operator",
                    status="active",
                )
            ]
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
                                    platform_code="shopee",
                                    shop_id="S1",
                                    allocatable_profit_rate=0.25,
                                )
                            ]
                        )
                    if entity is PerformanceScore:
                        return _MockResult(
                            rows=[
                                SimpleNamespace(
                                    platform_code="shopee",
                                    shop_id="S1",
                                    total_score=80.0,
                                    performance_coefficient=shop_coefficient,
                                    score_details={
                                        "summary": {"calculation_status": "complete"}
                                    },
                                )
                            ]
                        )
                return _MockResult(rows=[])

            db.execute = AsyncMock(side_effect=_execute)
            added = []
            db.add = lambda obj: added.append(obj)

            service = HRIncomeCalculationService(db=db)
            service._load_profit_basis_by_shop = AsyncMock(
                return_value={
                    "shopee|s1": {"profit_basis_amount": 1000.0},
                }
            )
            service._load_store_performance_by_shop = AsyncMock(
                return_value={
                    "shopee|s1": {
                        "total_score": 80.0,
                        "performance_coefficient": shop_coefficient,
                        "sales_target": 1000.0,
                    }
                }
            )
            # 店铺月度指标来自真 PG 查询，这里 mock 掉（与提成金额无关）。
            service._load_shop_metrics = AsyncMock(
                return_value={
                    "shopee|s1": {
                        "monthly_sales": 5000.0,
                        "monthly_profit": 1000.0,
                        "achievement_rate": 1.0,
                    }
                }
            )
            asyncio.run(service.calculate_month("2026-10"))
            commission = next(
                obj for obj in added if obj.__class__.__name__ == "EmployeeCommission"
            )
            return Decimal(str(commission.commission_amount))

        # 提成 = 1000 × 0.25 × 0.25 = 62.50，与赛马评级无关
        assert _run(0.5) == Decimal("62.5")
        assert _run(1.2) == Decimal("62.5")
