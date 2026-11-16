"""尾程配送费：纯函数（**无 ORM、无 DB**）。

业务概念
--------
尾程 = 仓 → 买家那段快递费。它**每卖一件必付**（头程是已付库存成本，一次性的）。
「这个平台 × 这个仓我们包邮」= 这个维度配了尾程费率 ⇒ 这笔成本由商家承担。

费率粒度
--------
``平台 × 仓 × 重量段``。重量段区间是 ``[min_weight_kg, max_weight_kg]``，
``max_weight_kg IS NULL`` 表示「往上不封顶」。

三条硬规则
----------
1. **区间重叠 ⇒ 歧义，不猜。** 两档同时命中就是配置错了；猜一个会让成本悄悄错掉
   （宁可算不出来，也不要算错）。返回 ``missing_reasons=('ambiguous_delivery_tier',)``。
2. **缺重量 ⇒ 保守估算并标记。** 不知道重量 ⇒ 不知道落在哪一档 ⇒ 取「该仓最轻档」
   与「同平台最贵仓的最轻档」中**更贵**的那个当估算值，并标 ``estimated=True``。
   让底线算不出来不是好结果（运营会以为系统坏了），但**必须标出来**它是估的。
3. **没配费率 ≠ 尾程免费。** 该平台 × 仓没有费率 ⇒ ``missing_reasons=('missing_delivery_rate',)``，
   金额留空。绝不能默认 0（默认 0 = 白送运费，利润虚高）。

本模块只做计算，**不碰数据库** —— 取数在 ``product_finance_service``，
选档与算钱在这里，保证同一份口径能在候选列表、单行试算、利润版本里复用。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Optional, Sequence

#: 金额量化：与商品中心其它金额一致（两位小数，ROUND_HALF_UP）。
MONEY_QUANTUM = Decimal("0.01")

#: 缺原因取值（前端 / 后端按这些码显示文案）。
MISSING_RATE = "missing_delivery_rate"
MISSING_WEIGHT = "missing_weight"
AMBIGUOUS_TIER = "ambiguous_delivery_tier"
WEIGHT_ABOVE_TOP_TIER = "weight_above_top_tier"


@dataclass(frozen=True)
class DeliveryTier:
    """一条重量段费率（纯数据，不带 ORM）。"""

    min_weight_kg: Decimal
    max_weight_kg: Optional[Decimal]
    unit_price: Decimal
    currency: str = "CNY"
    #: 所属仓（缺重量时用来挑「最贵仓」）。纯函数不依赖 ORM，仓信息靠它带进来。
    warehouse_code: str = ""


@dataclass(frozen=True)
class DeliveryCostResult:
    """尾程配送费的计算结果。

    ``amount`` 为 None ⇒ **算不出来**（看 ``missing_reasons``）；
    ``estimated=True`` ⇒ 算出来了，但它是**估的**，不能当实测值用。
    """

    amount: Optional[Decimal]
    source: str  # rate_table | estimated | unavailable
    estimated: bool
    missing_reasons: tuple[str, ...] = ()
    tier_min_weight_kg: Optional[Decimal] = None
    tier_max_weight_kg: Optional[Decimal] = None
    currency: str = "CNY"

    @property
    def computable(self) -> bool:
        return self.amount is not None


def _money(value: Decimal | int | float) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _decimal(value: Decimal | int | float | None) -> Optional[Decimal]:
    if value is None:
        return None
    return Decimal(str(value))


def _covers(tier: DeliveryTier, weight_kg: Decimal) -> bool:
    """重量是否落在这档里。

    区间是**左闭右开** ``[min_weight_kg, max_weight_kg)``：
    相邻两档 ``[0, 0.5)`` / ``[0.5, ∞)`` **不重叠**（边界归下一档），
    这样重量段才能连续铺开而不会互相打架。``max_weight_kg is None`` = 往上不封顶。
    """
    if weight_kg < tier.min_weight_kg:
        return False
    if tier.max_weight_kg is None:
        return True
    return weight_kg < tier.max_weight_kg


def match_delivery_tiers(
    tiers: Iterable[DeliveryTier], weight_kg: Decimal | int | float
) -> list[DeliveryTier]:
    """返回**所有**命中该重量的档位。

    命中 0 档 = 该重量没被费率覆盖；命中 ≥2 档 = 配置重叠（歧义）。
    """
    weight = Decimal(str(weight_kg))
    return [tier for tier in tiers if _covers(tier, weight)]


def select_delivery_tier(
    tiers: Iterable[DeliveryTier], weight_kg: Decimal | int | float
) -> Optional[DeliveryTier]:
    """按重量选档 —— **只在恰好命中一档**时返回。

    命中多档（配置重叠）返回 None：**歧义不猜**。
    """
    matched = match_delivery_tiers(tiers, weight_kg)
    if len(matched) != 1:
        return None
    return matched[0]


def _lightest_tier(tiers: Sequence[DeliveryTier]) -> Optional[DeliveryTier]:
    """该仓最轻的一档（重量下限最小的那档）—— 缺重量时的兜底基准。"""
    if not tiers:
        return None
    return min(tiers, key=lambda tier: (tier.min_weight_kg, tier.unit_price))


def _fallback_amount(
    tiers: Sequence[DeliveryTier], fallback_tiers: Sequence[DeliveryTier]
) -> Optional[Decimal]:
    """缺重量时的保守估：max(本仓最轻档, 同平台**最贵仓**的最轻档)。

    「最贵仓」= 其它仓里**最轻档单价最高**的那个仓（宁高不低）。
    """
    candidates: list[Decimal] = []
    local = _lightest_tier(tiers)
    if local is not None:
        candidates.append(local.unit_price)
    # 其它仓：每个仓只取它自己的**最轻档**，再在这些仓里挑最贵的那个。
    lightest_by_warehouse: dict[str, DeliveryTier] = {}
    for tier in fallback_tiers:
        current = lightest_by_warehouse.get(tier.warehouse_code)
        if current is None or tier.min_weight_kg < current.min_weight_kg:
            lightest_by_warehouse[tier.warehouse_code] = tier
    for tier in lightest_by_warehouse.values():
        candidates.append(tier.unit_price)
    if not candidates:
        return None
    return max(candidates)


def compute_delivery_cost(
    tiers: Sequence[DeliveryTier],
    weight_kg: Decimal | int | float | None,
    *,
    fallback_tiers: Sequence[DeliveryTier] = (),
) -> DeliveryCostResult:
    """算尾程配送费。

    参数
    ----
    tiers:
        该 **平台 × 仓** 的重量段费率（当期有效行）。
    weight_kg:
        SKU 单件重量。``None`` ⇒ 走保守估算（并标 ``estimated``）。
    fallback_tiers:
        同平台**其它仓**的费率（缺重量时用来取「最贵仓」做保守估算）。

    返回
    ----
    ``DeliveryCostResult``：金额为 None 时看 ``missing_reasons``。
    """
    if not tiers:
        return DeliveryCostResult(
            amount=None,
            source="unavailable",
            estimated=False,
            missing_reasons=(MISSING_RATE,),
        )

    weight = _decimal(weight_kg)

    if weight is None:
        # 缺重量 ⇒ 保守估算（该仓最轻档 vs 最贵仓，取更贵的）。
        amount = _fallback_amount(tiers, fallback_tiers)
        if amount is None:
            return DeliveryCostResult(
                amount=None,
                source="unavailable",
                estimated=False,
                missing_reasons=(MISSING_RATE,),
            )
        local = _lightest_tier(tiers)
        return DeliveryCostResult(
            amount=_money(amount),
            source="estimated",
            estimated=True,
            missing_reasons=(MISSING_WEIGHT,),
            tier_min_weight_kg=local.min_weight_kg if local else None,
            tier_max_weight_kg=local.max_weight_kg if local else None,
            currency=(local.currency if local else "CNY"),
        )

    matched = match_delivery_tiers(tiers, weight)
    if len(matched) > 1:
        # 配置重叠 ⇒ 歧义不猜（宁可算不出来，也不要算错）。
        return DeliveryCostResult(
            amount=None,
            source="unavailable",
            estimated=False,
            missing_reasons=(AMBIGUOUS_TIER,),
        )
    if len(matched) == 1:
        tier = matched[0]
        return DeliveryCostResult(
            amount=_money(tier.unit_price),
            source="rate_table",
            estimated=False,
            tier_min_weight_kg=tier.min_weight_kg,
            tier_max_weight_kg=tier.max_weight_kg,
            currency=tier.currency,
        )

    # 重量超出所有档位（且没有不封顶的档）⇒ 用最重的那档兜底，标 estimated。
    top = max(tiers, key=lambda tier: tier.min_weight_kg)
    return DeliveryCostResult(
        amount=_money(top.unit_price),
        source="estimated",
        estimated=True,
        missing_reasons=(WEIGHT_ABOVE_TOP_TIER,),
        tier_min_weight_kg=top.min_weight_kg,
        tier_max_weight_kg=top.max_weight_kg,
        currency=top.currency,
    )
