"""绩效工资口径守护：绩效工资 == 绩效包 × **纯个人**分数档位系数。

背景（ADR-2026-11-21）：绩效工资的系数在历史月份之间换过口径 ——
2026-07 是「绩效分数 ÷ 100」（纯个人），2026-10 是「逐店结算系数的
销售额加权平均」（含店铺赛马排名）⇒ 同一字段跨月不可比。

现在口径固定为：**绩效包金额 × 纯个人的绩效分数档位系数**，
与店铺排名无关。本守护锁死这一条。
"""

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.commission_caliber import calculate_employee_performance_salary
from backend.services.performance_coefficient import (
    SCORE_BAND_COEFFICIENTS,
    calculate_score_coefficient,
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


class TestScoreBandTable:
    """档位表本身的边界（唯一真源 ``SCORE_BAND_COEFFICIENTS``）。"""

    @pytest.mark.parametrize(
        "score,expected",
        [
            (100.0, 1.2),
            (95.0, 1.2),
            (90.0, 1.2),
            (89.9, 1.0),
            (80.0, 1.0),
            (79.9, 0.9),
            (70.0, 0.9),
            (69.9, 0.8),
            (60.0, 0.8),
            (59.9, 0.5),
            (0.0, 0.5),
        ],
    )
    def test_band_boundaries(self, score, expected):
        assert calculate_score_coefficient(score) == expected

    def test_table_has_no_zero_coefficient(self):
        """档位表不得出现 0 系数 —— 0 只表示「未完成考核」。"""
        for _, coefficient in SCORE_BAND_COEFFICIENTS:
            assert coefficient > 0

    def test_table_is_monotonic_non_increasing(self):
        """分数越高，系数不得越低。"""
        coefficients = [c for _, c in SCORE_BAND_COEFFICIENTS]
        assert coefficients == sorted(coefficients, reverse=True)


class TestPerformanceSalaryCaliber:
    """绩效工资 = 绩效包 × 纯个人分数档位系数。"""

    @pytest.mark.parametrize(
        "score,package,expected",
        [
            (85.0, 1000, 1000.0),
            (95.0, 1000, 1200.0),
            (75.0, 1000, 900.0),
            (65.0, 1000, 800.0),
            (55.0, 1000, 500.0),
        ],
    )
    def test_package_times_score_coefficient(self, score, package, expected):
        assert (
            float(
                calculate_employee_performance_salary(
                    performance_package_amount=package,
                    performance_score_coefficient=calculate_score_coefficient(score),
                )
            )
            == expected
        )

    def test_multi_shop_employee_uses_same_personal_coefficient(self):
        """多店员工：绩效工资**只**看个人分数，与他在几家店无关。"""
        from backend.services.payroll_generation_service import (
            PayrollGenerationService,
        )

        package = Decimal("1000")
        score = 85.0

        for _ in range(3):
            salary = SimpleNamespace(
                employee_code="EMP001",
                base_salary=Decimal("0"),
                position_salary=Decimal("0"),
                performance_package_amount=package,
                housing_allowance=Decimal("0"),
                transport_allowance=Decimal("0"),
                meal_allowance=Decimal("0"),
                communication_allowance=Decimal("0"),
                other_allowance=Decimal("0"),
                performance_ratio=0.2,
                status="active",
            )
            performance = SimpleNamespace(
                employee_code="EMP001",
                year_month="2026-10",
                performance_score=score,
                # ⚠️ 故意给一个「含店铺排名」的旧值（0.7655），
                # 验证新口径**不会**用它。
                performance_coefficient=0.7655,
                calculation_status="complete",
                performance_source_type="shop_inherited",
            )
            db = AsyncMock()

            async def _execute(stmt, params=None):
                from modules.core.db import (
                    EmployeeCommission,
                    EmployeePerformance,
                    PayrollRecord,
                    SalaryStructure,
                )

                if hasattr(stmt, "column_descriptions"):
                    entity = stmt.column_descriptions[0].get("entity")
                    if entity is SalaryStructure:
                        return _MockResult(rows=[salary])
                    if entity is EmployeeCommission:
                        return _MockResult(rows=[])
                    if entity is EmployeePerformance:
                        return _MockResult(rows=[performance])
                    if entity is PayrollRecord:
                        return _MockResult(rows=[])
                return _MockResult(rows=[])

            db.execute = AsyncMock(side_effect=_execute)
            added = []
            db.add = lambda obj: added.append(obj)

            asyncio.run(PayrollGenerationService(db=db).generate_month("2026-10"))
            record = next(
                obj for obj in added if obj.__class__.__name__ == "PayrollRecord"
            )
            # 85 分 → 档位系数 1.0 ⇒ 1000 × 1.0 = 1000
            # （若用旧的 performance_coefficient=0.7655 ⇒ 765.50）
            assert float(record.performance_salary) == 1000.0

    def test_incomplete_controlled_performance_gives_zero(self):
        """「未完成考核」⇒ 绩效工资 0（口径不变）。"""
        from backend.services.payroll_generation_service import (
            PayrollGenerationService,
        )

        performance = SimpleNamespace(
            employee_code="EMP001",
            year_month="2026-10",
            performance_score=95.0,
            performance_coefficient=1.2,
            calculation_status="pending",
            performance_source_type="controlled_targets_v1",
        )
        coefficient = PayrollGenerationService._normalize_performance_coefficient(
            performance
        )
        assert coefficient == Decimal("0")

    def test_missing_score_gives_zero(self):
        """没有绩效分数 ⇒ 没有档位系数 ⇒ 绩效工资 0。"""
        from backend.services.payroll_generation_service import (
            PayrollGenerationService,
        )

        performance = SimpleNamespace(
            employee_code="EMP001",
            year_month="2026-10",
            performance_score=None,
            performance_coefficient=0.7655,
            calculation_status="complete",
            performance_source_type="shop_inherited",
        )
        coefficient = PayrollGenerationService._normalize_performance_coefficient(
            performance
        )
        assert coefficient == Decimal("0")


class TestNoShopRankingInPerformanceSalary:
    """赛马排名不得影响绩效工资。"""

    def test_two_employees_same_score_same_package_same_salary(self):
        """分数相同 ⇒ 绩效工资相同（与各自店铺排名无关）。"""
        package = Decimal("1000")
        for score in (85.0, 85.0):
            assert (
                float(
                    calculate_employee_performance_salary(
                        performance_package_amount=package,
                        performance_score_coefficient=calculate_score_coefficient(
                            score
                        ),
                    )
                )
                == 1000.0
            )

    def test_caliber_module_does_not_accept_shop_coefficient(self):
        """真源函数的签名里**没有**店铺系数入口 —— 结构上杜绝赛马混入。"""
        import inspect

        from backend.services.commission_caliber import (
            calculate_employee_performance_salary,
        )

        params = set(
            inspect.signature(calculate_employee_performance_salary).parameters
        )
        assert "performance_score_coefficient" in params
        assert not any(
            "shop" in name or "ranking" in name or "rank" in name for name in params
        ), f"绩效工资函数不该接受店铺排名相关入参：{params}"
