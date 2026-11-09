"""统一结算系数（SSOT）。

业务口径：**一个系数，同时决定「绩效工资」和「提成」**。

    月度结算系数 = min( 排名档位系数 , 分数档位系数 )

两条轴，各有且只有一张档位表（见下方常量），任何模块都不得再自定义档位：

* **排名档位系数**：店铺当月在正式排名池里的名次档位。
* **分数档位系数**：绩效分数的分数档位。

派生关系：

    店铺结算系数 = min(该店排名档位系数, 该店分数档位系数)
    员工结算系数 = min(该店结算系数, 员工分数档位系数)

改造前这两件事是分开的：

* 提成乘「店铺排名系数」（0.5 ~ 1.2，来自 ``calculate_score_cap_coefficient``）
* 绩效工资乘「绩效分数 ÷ 100」（0 ~ 1，来自 ``PayrollGenerationService``）

于是同一个人同一个月有两套系数，页面显示的和工资单实发对不上
（2026-10 实测：页面 1002.56 / 后端统计 1002.55 / 实发 979.46）。

现在统一成一条链路：**页面看到的系数，就是工资单拿到的系数**。
"""

from __future__ import annotations

from typing import Any, Iterable


# ------------------------------------------------------------------ 档位表（SSOT）
# 排名档位：正式排名池里的名次占比 -> 系数
RANK_BAND_COEFFICIENTS = (
    (0.20, 1.2),
    (0.50, 1.0),
    (0.80, 0.9),
)
# 排名落在 80% 之后的系数
RANK_BAND_FLOOR = 0.8

# 分数档位：绩效分数 -> 系数
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
    """给接口/页面用的可解释拆解：哪个约束把系数压下来了。"""
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
