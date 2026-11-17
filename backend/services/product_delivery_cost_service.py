"""尾程配送费：纯函数（**无 ORM、无 DB**）。

业务概念
--------
尾程 = 仓 → 买家那段快递费。它**每卖一件必付**（头程是已付库存成本，一次性的）。
「这个平台 × 这个仓我们包邮」= 这个维度配了尾程费率 ⇒ 这笔成本由商家承担。

费率粒度
--------
``平台 × 仓 × 重量段``。重量段是**全局一套**（``core.dim_weight_tiers``），
SKU 报「落在哪一段」，费率表报「这一段多少钱」。

批次 6（2026-11-17）的口径变化
--------------------------
承运商按**重量段**定价（Shopee SG / TikTok SG 价目表都是「≤1kg / ≤5kg / … 一档价」），
所以 SKU **不再称重**，只选段 ⇒ 老的「按 kg 落区间」这套选档逻辑整体退役，
本模块改成**按段编码命中**。

四条硬规则
----------
1. **该段没配价 ≠ 尾程免费。** 该平台 × 仓没有费率 ⇒
   ``missing_reasons=('missing_delivery_rate',)``，金额留空。
   段配了费率但**这一段没配价** ⇒ ``('missing_delivery_rate_for_tier',)``，
   金额同样留空。绝不能默认 0（默认 0 = 白送运费，利润虚高）。
2. **未选段 ⇒ 默认最轻段，并标出来。** 用户 2026-11-17 拍板：SKU 没选段时按
   **最轻段**算（估），标 ``estimated=True`` + ``missing_weight_tier``。
   ⚠️ 最轻段通常是最便宜的一档 ⇒ 这是**偏乐观**口径，界面必须提示「重货务必选段」。
3. **跨仓取最贵。** 估算时取「本平台各仓该段价」的**最大值**（宁高不低），
   避免从哪个仓发都算出偏低的尾程。
4. **同一段配了两行 ⇒ 歧义，不猜。** 返回 ``('ambiguous_delivery_tier',)``，
   金额留空（宁可算不出来，也不要算错）。

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
#: 该平台 × 仓有费率表，但**这一段**没配价。
MISSING_TIER_RATE = "missing_delivery_rate_for_tier"
#: SKU 没选重量段 ⇒ 按最轻段估算。
MISSING_WEIGHT_TIER = "missing_weight_tier"
#: 同一段配了两行当期费率 ⇒ 选档歧义。
AMBIGUOUS_TIER = "ambiguous_delivery_tier"


@dataclass(frozen=True)
class DeliveryTier:
    """一条重量段费率（纯数据，不带 ORM）。

    ⚠️ **段是全局的**：``tier_code`` 相同 ⇒ 指的是同一个重量区间，
    不管来自哪个仓、哪个平台。
    """

    tier_code: str
    label: str
    min_weight_kg: Decimal
    max_weight_kg: Optional[Decimal]
    unit_price: Decimal
    currency: str = "CNY"
    #: 所属仓（估算时用来挑「最贵仓」）。纯函数不依赖 ORM，仓信息靠它带进来。
    warehouse_code: str = ""
    #: 段在全局段表里的顺序（轻 → 重）。用于「最轻段」的稳定排序。
    sort_order: int = 0


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
    tier_code: Optional[str] = None
    tier_label: Optional[str] = None
    tier_min_weight_kg: Optional[Decimal] = None
    tier_max_weight_kg: Optional[Decimal] = None
    currency: str = "CNY"

    @property
    def computable(self) -> bool:
        return self.amount is not None


def _money(value: Decimal | int | float) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def match_delivery_tiers(
    tiers: Iterable[DeliveryTier], tier_code: str
) -> list[DeliveryTier]:
    """返回**所有**命中该段编码的档位。

    命中 0 档 = 该段没配价；命中 ≥2 档 = 配置重复（歧义）。
    """
    return [tier for tier in tiers if tier.tier_code == tier_code]


def select_tier_by_code(
    tiers: Iterable[DeliveryTier], tier_code: str
) -> Optional[DeliveryTier]:
    """按段编码选档 —— **只在恰好命中一档**时返回。

    命中多档（配置重复）返回 None：**歧义不猜**。
    """
    matched = match_delivery_tiers(tiers, tier_code)
    if len(matched) != 1:
        return None
    return matched[0]


def _lightest_tier(tiers: Sequence[DeliveryTier]) -> Optional[DeliveryTier]:
    """全局最轻的一档 —— **未选段时的兜底基准**。

    「最轻」按 ``(sort_order, min_weight_kg)`` 取：
    段表全局一套 ⇒ 同一个段编码在任何仓都表示同一段，
    所以这里比较的是**段本身**，不是各仓各自的最轻档。
    """
    if not tiers:
        return None
    return min(tiers, key=lambda tier: (tier.sort_order, tier.min_weight_kg))


def _tier_prices(tiers: Sequence[DeliveryTier], tier_code: str) -> list[Decimal]:
    """各仓里该段的单价（可能来自多个仓）。"""
    return [tier.unit_price for tier in tiers if tier.tier_code == tier_code]


def compute_delivery_cost(
    tiers: Sequence[DeliveryTier],
    tier_code: str | None,
    *,
    fallback_tiers: Sequence[DeliveryTier] = (),
) -> DeliveryCostResult:
    """算尾程配送费。

    参数
    ----
    tiers:
        该 **平台 × 仓** 的重量段费率（当期有效行）。
    tier_code:
        SKU 落在哪一段。``None`` ⇒ 未选段 ⇒ 按**最轻段**估算（并标 ``estimated``）。
    fallback_tiers:
        同平台**其它仓**的费率（估算时用来取「最贵仓」做保守估值）。

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

    if tier_code is None:
        # 未选段 ⇒ 默认最轻段 + 保守估值（各仓该段价取最贵）。
        # ⚠️ 「最轻段」必须在**全局**范围内取（tiers + fallback_tiers）——
        #    否则各仓各挑各的最轻档，同一个段在不同仓含义就不一样了。
        lightest = _lightest_tier(list(tiers) + list(fallback_tiers))
        if lightest is None:
            return DeliveryCostResult(
                amount=None,
                source="unavailable",
                estimated=False,
                missing_reasons=(MISSING_RATE,),
            )
        prices = _tier_prices(list(tiers) + list(fallback_tiers), lightest.tier_code)
        if not prices:
            return DeliveryCostResult(
                amount=None,
                source="unavailable",
                estimated=False,
                missing_reasons=(MISSING_RATE,),
            )
        return DeliveryCostResult(
            amount=_money(max(prices)),
            source="estimated",
            estimated=True,
            missing_reasons=(MISSING_WEIGHT_TIER,),
            tier_code=lightest.tier_code,
            tier_label=lightest.label,
            tier_min_weight_kg=lightest.min_weight_kg,
            tier_max_weight_kg=lightest.max_weight_kg,
            currency=lightest.currency,
        )

    matched = match_delivery_tiers(tiers, tier_code)
    if len(matched) > 1:
        # 同一段配了两行当期费率 ⇒ 歧义不猜（宁可算不出来，也不要算错）。
        return DeliveryCostResult(
            amount=None,
            source="unavailable",
            estimated=False,
            missing_reasons=(AMBIGUOUS_TIER,),
        )
    if not matched:
        # 该段没配价 ⇒ 算不出来（≠ 免费）。
        return DeliveryCostResult(
            amount=None,
            source="unavailable",
            estimated=False,
            missing_reasons=(MISSING_TIER_RATE,),
        )

    tier = matched[0]
    return DeliveryCostResult(
        amount=_money(tier.unit_price),
        source="rate_table",
        estimated=False,
        tier_code=tier.tier_code,
        tier_label=tier.label,
        tier_min_weight_kg=tier.min_weight_kg,
        tier_max_weight_kg=tier.max_weight_kg,
        currency=tier.currency,
    )
