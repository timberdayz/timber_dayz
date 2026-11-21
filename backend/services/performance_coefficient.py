"""绩效档位表（SSOT）。

⚠️ **口径变更（ADR-2026-11-21）**：本文件不再是「一个系数同时决定绩效工资和提成」。

现在的职责划分：

* **绩效分数档位系数**（:data:`SCORE_BAND_COEFFICIENTS`）
  —— 唯一作用于**绩效工资**的系数：``绩效工资 = 绩效包金额 × 本档位系数``。
  纯个人，与店铺排名无关。
* **排名档位系数**（:data:`RANK_BAND_COEFFICIENTS`）
  —— 店铺赛马评级，**不参与任何金额**，只做考核、预警与展示。
* **结算系数**（``calculate_settlement_coefficient`` / ``describe_settlement_coefficient``）
  —— 上面两者的 ``min``。**已从金额链路移除**，仅保留用于**展示拆解**
  （让页面能说明「赛马评级多少、个人档位多少」，不参与计算结果）。

提成口径见 :mod:`backend.services.commission_caliber`：
``提成 = max(可分配利润, 0) × 归属提成比`` —— **零系数**。

两条轴，各有且只有一张档位表（见下方常量），任何模块都不得再自定义档位：

* **排名档位系数**：店铺当月在正式排名池里的名次档位。
* **分数档位系数**：绩效分数的分数档位。
"""

from __future__ import annotations

from typing import Any, Iterable


# ------------------------------------------------------------------ 档位表（SSOT）
# 排名档位：正式排名池里的名次占比 -> 系数（**仅考核展示，不参与金额**）
RANK_BAND_COEFFICIENTS = (
    (0.20, 1.2),
    (0.50, 1.0),
    (0.80, 0.9),
)
# 排名落在 80% 之后的系数
RANK_BAND_FLOOR = 0.8

# 分数档位：绩效分数 -> 系数（**绩效工资唯一入口**）
SCORE_BAND_COEFFICIENTS = (
    (90.0, 1.2),
    (80.0, 1.0),
    (70.0, 0.9),
    (60.0, 0.8),
)
# 分数低于 60 分的系数
SCORE_BAND_FLOOR = 0.5


def calculate_rank_band_coefficient(rank: int, total: int) -> float:
    """按名次占比给出排名档位系数。"""
    if total <= 0:
        return 1.0
    for ratio, coefficient in RANK_BAND_COEFFICIENTS:
        cutoff = max(1, int(total * ratio + 0.999999))
        if rank <= cutoff:
            return coefficient
    return RANK_BAND_FLOOR


def calculate_score_coefficient(score: Any) -> float:
    """按绩效分数给出分数档位系数。"""
    value = float(score or 0.0)
    for threshold, coefficient in SCORE_BAND_COEFFICIENTS:
        if value >= threshold:
            return coefficient
    return SCORE_BAND_FLOOR


def calculate_performance_coefficient(score: Any) -> float:
    """历史别名，等价于 :func:`calculate_score_coefficient`。

    保留旧名字是为了不打断既有调用方；新代码请用 ``calculate_score_coefficient``，
    以免和「店铺结算系数」混淆。
    """
    return calculate_score_coefficient(score)


def calculate_ranked_performance_coefficient(
    score: Any, rank: int, total: int
) -> float:
    """店铺结算系数 = min(排名档位系数, 分数档位系数)。"""
    return min(
        calculate_rank_band_coefficient(rank, total),
        calculate_score_coefficient(score),
    )


def calculate_settlement_coefficient(*coefficients: Any) -> float:
    """月度结算系数 = 所有约束项里最低的那个。

    ⚠️ **已从金额链路移除（ADR-2026-11-21）**：提成零系数、绩效工资用纯个人档位，
    这个函数**不再影响任何金额**，仅保留用于**展示拆解**。

    ``None`` 表示「这一项不构成约束」，会被忽略；一个约束都没有时返回 1.0。
    """
    values = [float(item) for item in coefficients if item is not None]
    if not values:
        return 1.0
    return min(values)


def describe_settlement_coefficient(
    shop_coefficient: Any = None,
    score_coefficient: Any = None,
) -> dict[str, Any]:
    """给接口/页面用的可解释拆解：赛马评级与个人档位各是多少。

    ⚠️ **仅展示，不参与任何金额**（ADR-2026-11-21）。

    ``shop_coefficient``  = 店铺赛马评级（来自 ``c_class.performance_scores``）
    ``score_coefficient`` = 员工个人绩效分数档位系数

    ``limited_by`` 保留原语义（哪一项更低），但它现在**只用于展示**。
    """
    shop_value = None if shop_coefficient is None else float(shop_coefficient)
    score_value = None if score_coefficient is None else float(score_coefficient)
    final = calculate_settlement_coefficient(shop_value, score_value)
    if shop_value is None and score_value is None:
        limited_by = None
    elif score_value is not None and (shop_value is None or score_value < shop_value):
        limited_by = "personal_score"
    else:
        limited_by = "shop_ranking"
    return {
        "settlement_coefficient": final,
        "shop_coefficient": shop_value,
        "score_coefficient": score_value,
        "limited_by": limited_by,
    }


def iter_settlement_constraints(values: Iterable[Any]) -> list[float]:
    """把约束项规整成数值列表，便于落审计字段。"""
    return [float(item) for item in values if item is not None]
