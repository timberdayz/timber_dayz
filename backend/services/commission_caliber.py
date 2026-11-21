"""提成与绩效工资公式 —— 唯一实现处（SSOT）。

业务口径（2026-11-21 业务确认）：

    某员工从某店分到的提成 = max(该店可分配利润, 0) × 该员工的归属提成比

    其中：该店可分配利润 = max(该店利润基数, 0) × 该店可分配利润率

    绩效工资 = 绩效包金额 × 绩效分数档位系数(该员工的绩效分数)

**提成三个因子、零系数：分多少，给多少。**
**绩效工资只乘个人分数档位系数，与店铺排名无关。**
**店铺赛马排名不参与任何金额**，只做考核与预警。

这个模块是**唯一**的实现：工资单计算、结算预览、店铺维度统计、月度结算单、
确认校验全部调它，避免同一句公式被抄多遍后各自漂移。

铁律
----
1. **不得**在函数内查库、读配置、取系数 —— 入参即全部输入（纯函数）；
2. 档位表不在这里定义 —— 档位表的唯一真源是
   :mod:`backend.services.performance_coefficient`；
3. 新增任何提成计算，必须调用这里的函数，不得就地复刻公式。
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Union

#: 金额量化精度（与工资单口径一致：分）
MONEY_QUANT = Decimal("0.01")

Number = Union[int, float, Decimal, str, None]


def to_decimal(value: Any) -> Decimal:
    """把任意数值输入转成 ``Decimal``；``None`` 与空串按 0 处理。

    走 ``Decimal(str(value))`` 而不是 ``Decimal(value)``：浮点数直接进
    ``Decimal`` 会带上二进制误差（0.1 变成 0.1000000000000000055511151231…），
    金额计算必须避开这条路径。
    """
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return Decimal("0")
        return Decimal(text)
    return Decimal(str(value))


def quantize_money(value: Any) -> Decimal:
    """按分位四舍五入（ROUND_HALF_UP），与工资单金额口径一致。"""
    return to_decimal(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def calculate_shop_allocatable_profit(
    profit_basis_amount: Number,
    allocatable_profit_rate: Number,
) -> Decimal:
    """该店当月的**可分配利润**。

    参数
    ----
    profit_basis_amount:
        该店当月的利润基数（真源：``finance.shop_profit_basis``）。
        **负数（亏损）按 0 处理** —— 亏损不产生可分配利润。
    allocatable_profit_rate:
        该店当月的可分配利润率（真源：``a_class.shop_commission_config``，
        人工配置，唯一来源）。未配置按 0 处理。

    返回
    ----
    ``Decimal``，未舍入（调用方决定在哪一步舍入）。
    """
    basis = to_decimal(profit_basis_amount)
    if basis < 0:
        basis = Decimal("0")
    rate = to_decimal(allocatable_profit_rate)
    if rate < 0:
        rate = Decimal("0")
    return basis * rate


def calculate_employee_shop_commission(
    allocatable_profit: Number,
    commission_ratio: Number,
) -> Decimal:
    """某员工从某店分到的提成。

    参数
    ----
    allocatable_profit:
        该店可分配利润（用 :func:`calculate_shop_allocatable_profit` 算）。
    commission_ratio:
        该员工在该店的归属提成比（真源：``a_class.employee_shop_assignments``，
        人工配置，唯一来源）。负数按 0 处理。

    返回
    ----
    ``Decimal``，未舍入（尾差由调用方统一吸收）。

    ⚠️ 这里**不再乘任何系数**。店铺赛马排名与个人分数档位都不参与提成金额。
    """
    profit = to_decimal(allocatable_profit)
    if profit < 0:
        profit = Decimal("0")
    ratio = to_decimal(commission_ratio)
    if ratio < 0:
        ratio = Decimal("0")
    return profit * ratio


def calculate_employee_commission(
    profit_basis_amount: Number,
    allocatable_profit_rate: Number,
    commission_ratio: Number,
) -> Decimal:
    """便捷入口：一步算完「某员工从某店分到的提成」。

    等价于::

        calculate_employee_shop_commission(
            calculate_shop_allocatable_profit(basis, rate),
            ratio,
        )
    """
    return calculate_employee_shop_commission(
        calculate_shop_allocatable_profit(profit_basis_amount, allocatable_profit_rate),
        commission_ratio,
    )


def calculate_employee_performance_salary(
    performance_package_amount: Number,
    performance_score_coefficient: Number,
) -> Decimal:
    """员工绩效工资 = 绩效包金额 × 绩效分数档位系数。

    参数
    ----
    performance_package_amount:
        绩效包金额（真源：``a_class.salary_structures.performance_package_amount``，
        人工配置，唯一来源）。
    performance_score_coefficient:
        **纯个人**的绩效分数档位系数（真源：
        :data:`backend.services.performance_coefficient.SCORE_BAND_COEFFICIENTS`，
        经 ``calculate_score_coefficient(绩效分数)`` 得出）。

        ⚠️ 这里传入的必须是**个人分数档位系数**，
        **不是**「逐店结算系数的加权平均」（那已不是纯个人口径）。
    """
    package = to_decimal(performance_package_amount)
    if package < 0:
        package = Decimal("0")
    coefficient = to_decimal(performance_score_coefficient)
    if coefficient < 0:
        coefficient = Decimal("0")
    return package * coefficient
