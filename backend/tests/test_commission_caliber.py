"""``commission_caliber`` 纯函数单元测试（提成公式唯一实现处）。

这些用例不碰数据库 —— 提成公式的唯一真源必须能被**秒级**验证，
任何算错都在这里当场暴露，而不是等到工资单跑出来才发现。
"""

from decimal import Decimal

import pytest

from backend.services.commission_caliber import (
    calculate_employee_commission,
    calculate_employee_performance_salary,
    calculate_employee_shop_commission,
    calculate_shop_allocatable_profit,
    quantize_money,
    to_decimal,
)


class TestToDecimal:
    def test_none_and_empty_string_become_zero(self):
        assert to_decimal(None) == Decimal("0")
        assert to_decimal("") == Decimal("0")
        assert to_decimal("   ") == Decimal("0")

    def test_float_does_not_leak_binary_error(self):
        # Decimal(0.1) 直接转会带上二进制尾数；Decimal(str(0.1)) 不会。
        assert to_decimal(0.1) == Decimal("0.1")
        assert str(to_decimal(0.1)) == "0.1"

    def test_decimal_passes_through(self):
        assert to_decimal(Decimal("12.34")) == Decimal("12.34")

    def test_numeric_string_is_parsed(self):
        assert to_decimal("12.34") == Decimal("12.34")
        assert to_decimal("-12.34") == Decimal("-12.34")


class TestQuantizeMoney:
    def test_rounds_half_up_to_cents(self):
        assert quantize_money(Decimal("1.005")) == Decimal("1.01")
        assert quantize_money(Decimal("1.004")) == Decimal("1.00")
        assert quantize_money(Decimal("2.345")) == Decimal("2.35")


class TestCalculateShopAllocatableProfit:
    def test_positive_basis_times_rate(self):
        assert calculate_shop_allocatable_profit(1000, 0.25) == Decimal("250")

    def test_negative_basis_is_clamped_to_zero(self):
        # 亏损店不产生可分配利润 —— 这是「负数归零」的第一道关。
        assert calculate_shop_allocatable_profit(-500, 0.25) == Decimal("0")

    def test_zero_rate_yields_zero(self):
        assert calculate_shop_allocatable_profit(1000, 0) == Decimal("0")

    def test_negative_rate_is_clamped_to_zero(self):
        assert calculate_shop_allocatable_profit(1000, -0.25) == Decimal("0")

    def test_missing_inputs_are_zero(self):
        assert calculate_shop_allocatable_profit(None, None) == Decimal("0")


class TestCalculateEmployeeShopCommission:
    def test_ratio_multiplication(self):
        assert calculate_employee_shop_commission(1000, 0.25) == Decimal("250")

    def test_negative_ratio_is_clamped_to_zero(self):
        assert calculate_employee_shop_commission(1000, -0.25) == Decimal("0")

    def test_negative_profit_is_clamped_to_zero(self):
        assert calculate_employee_shop_commission(-1000, 0.25) == Decimal("0")

    def test_no_coefficient_is_applied(self):
        """回归防线：提成公式里不得再出现任何系数。

        同一条可分配利润，无论赛马评级、绩效分数如何，
        提成金额都只由「可分配利润 × 归属提成比」决定。
        """
        allocatable_profit = Decimal("1000")
        ratio = Decimal("0.25")
        assert calculate_employee_shop_commission(allocatable_profit, ratio) == (
            Decimal("250")
        )


class TestCalculateEmployeeCommission:
    def test_end_to_end(self):
        assert calculate_employee_commission(1000, 0.25, 0.25) == Decimal("62.5")

    def test_loss_shop_gives_zero(self):
        assert calculate_employee_commission(-1000, 0.25, 0.25) == Decimal("0")

    def test_equals_two_step_composition(self):
        """便捷入口必须与两步写法**完全一致**（否则又是第二套算法）。"""
        step = calculate_employee_shop_commission(
            calculate_shop_allocatable_profit(1234.56, 0.3),
            0.15,
        )
        direct = calculate_employee_commission(1234.56, 0.3, 0.15)
        assert step == direct


class TestCalculateEmployeePerformanceSalary:
    def test_package_times_personal_score_coefficient(self):
        assert calculate_employee_performance_salary(2000, 0.9) == Decimal("1800")

    def test_full_score_band_top(self):
        assert calculate_employee_performance_salary(2000, 1.2) == Decimal("2400")

    def test_floor_band(self):
        assert calculate_employee_performance_salary(2000, 0.5) == Decimal("1000")

    def test_zero_coefficient_gives_zero(self):
        assert calculate_employee_performance_salary(2000, 0) == Decimal("0")

    def test_negative_package_is_clamped(self):
        assert calculate_employee_performance_salary(-2000, 1.0) == Decimal("0")


class TestRoundingContract:
    def test_results_are_decimal_not_float(self):
        """金额必须是 ``Decimal`` —— float 会把 1 分钱误差带进工资单。"""
        result = calculate_employee_commission(100, 0.1, 0.1)
        assert isinstance(result, Decimal)

    def test_repeated_call_is_stable(self):
        """幂等：同样的输入必须给出同样的结果（不得有内部状态）。"""
        first = calculate_employee_commission(333.33, 0.25, 0.3)
        second = calculate_employee_commission(333.33, 0.25, 0.3)
        assert first == second


@pytest.mark.parametrize(
    "basis,rate,ratio,expected",
    [
        (0, 0.25, 0.25, Decimal("0")),
        (100, 0, 0.25, Decimal("0")),
        (100, 0.25, 0, Decimal("0")),
        (100, 1.0, 1.0, Decimal("100")),
        (10000, 0.15, 0.35, Decimal("525")),
    ],
)
def test_parameter_matrix(basis, rate, ratio, expected):
    assert calculate_employee_commission(basis, rate, ratio) == expected
