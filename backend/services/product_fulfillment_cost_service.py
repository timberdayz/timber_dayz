"""履约按件成本（**头程 / 仓储 / 贴单**）的**唯一**取数与计算。

批次 9 P2（2026-11-19 拍板）：这三项是**按件的钱** ⇒ 进成本底线**分子**。

口径
----
- **头程** ``logistics_cost``：收货仓的物流商规则（``finance.logistics_provider_rules``）
  单价 × 单件体积（按体积计费）或重量段代表重量（按重量计费）⇒ 元/件。
- **仓储** ``storage_cost``：收货仓的仓储规则（``finance.warehouse_storage_rules``，
  CNY/CBM/月）× 单件体积 × 周转天数/30 ⇒ 元/件。
- **贴单** ``label_fee``：收货仓**仓储规则**上的每件贴单费 ⇒ 元/件。

缺料纪律（批次 9 定）
----------------------
这三项是「**逐步补齐型**」缺料：缺一项 ⇒ 该项**未计入**底线（**不是 0 成本**），
但**仍然出底线**，并在 ``missing_reasons`` 里点名。
与采购成本 / SPU 两率 / 平台费率这类「不可省略型」缺料**刻意不同** ——
后者缺了 ⇒ **不算底线**。

⚠️ 为什么缺体积也照样出底线：生产上 1122 个 SKU 只有 **18 个**录了体积
（``core.dim_erp_sku.unit_volume_cbm``，三个旧尺寸列 ``package_*_cm`` 全空）。
若按「缺失即留白」处理，1104 个 SKU 会直接失去底线 ——
那是把「数据没录」变成「系统不管」，比「底线偏松」严重得多。
偏松要**显式标注**（``missing_unit_volume``），让运营知道这个底线还没算全。

⚠️ **运输方式不进底线**：底线是「SKU × 平台 × 仓」的量，运输方式属于
**发运批次**维度 ⇒ 同一 SKU 换个发运批次底线就跳一次，那不是成本变化。
所以这里取「该仓**不限运输方式**时唯一可确定的那条规则」；
挑不出来（多条费率不同的 default）⇒ **不计入**（宁可不算，也不要算错）。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import (
    DimErpSku,
    DimWeightTier,
    LogisticsProviderRule,
    WarehouseStorageRule,
)

from .product_profit_service import build_reference_storage_cost, reference_storage_days

MONEY_QUANTUM = Decimal("0.01")

#: 履约成本的缺料原因（界面据此提示「未计入」，并说明缺什么）。
MISSING_WAREHOUSE = "missing_warehouse_for_fulfillment"
MISSING_LOGISTICS_RULE = "missing_logistics_provider_rule"
MISSING_STORAGE_RULE = "missing_warehouse_storage_rule"
MISSING_UNIT_VOLUME = "missing_unit_volume"
MISSING_TURNOVER_CLASS = "missing_turnover_class"
MISSING_WEIGHT_TIER = "missing_sku_weight_tier"


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def unit_volume_cbm(sku) -> Optional[Decimal]:
    """单件体积（CBM）：**维护值优先**，旧三维尺寸兜底；没有就是 ``None``。

    ⚠️ 与 ``product_finance_service._unit_volume_cbm`` 的差别是**刻意的**：
    那一个用于**账单分摊**，缺尺寸时按 0（分摊总额不变）；
    这里用于**成本底线**，缺尺寸必须报「未计入」而不是按 0 ——
    按 0 = 假装这个货不占体积 = 头程与仓储成本凭空消失。
    """
    if sku.unit_volume_cbm is not None:
        return Decimal(str(sku.unit_volume_cbm))
    dimensions = (sku.package_length_cm, sku.package_width_cm, sku.package_height_cm)
    if any(value is None for value in dimensions):
        return None
    return Decimal(str(dimensions[0] * dimensions[1] * dimensions[2])) / Decimal(
        "1000000"
    )


def tier_representative_weight_kg(tier) -> Decimal:
    """重量段的**代表重量** = 段上限（不封顶段取下限）—— 宁高不低。

    SKU 不存精确重量（``weight_kg`` 已退役），但仍有按重量计费的规则。
    用段上限当代表值：比真实重量大 ⇒ 成本估高 ⇒ 底线偏保守。
    """
    if tier is None:
        return Decimal("0")
    if tier.max_kg is not None:
        return Decimal(str(tier.max_kg))
    return Decimal(str(tier.min_kg))


def select_logistics_rule(
    rules: Iterable, warehouse_code: Optional[str], transport_type: Optional[str] = None
):
    """在候选规则里挑**唯一**一条；挑不出来就返回 ``None``（宁可不算，也不要算错）。

    优先级：仓匹配 > 运输方式匹配 > 唯一 default。
    同优先级有两条且都不是唯一 default ⇒ **歧义** ⇒ 返回 ``None``。

    ``transport_type=None`` = **不限运输方式**（底线链用，见模块头）。
    """
    rows = [rule for rule in rules if rule is not None]
    if not rows:
        return None

    def specificity(rule) -> int:
        return int(rule.warehouse_code == warehouse_code) + int(
            rule.transport_type == transport_type
        )

    highest = max(specificity(rule) for rule in rows)
    best = [rule for rule in rows if specificity(rule) == highest]
    if len(best) == 1:
        return best[0]
    defaults = [rule for rule in best if rule.is_default]
    return defaults[0] if len(defaults) == 1 else None


def compute_fulfillment_costs(
    *,
    unit_volume: Optional[Decimal],
    turnover_class: Optional[str],
    logistics_rule,
    storage_rule,
    weight_tier=None,
) -> dict:
    """一个 SKU 的履约按件成本（头程 / 仓储 / 贴单）+ 缺料原因。

    ``None`` = **该项未计入**（缺输入），**不是 0**。
    """
    reasons: list[str] = []

    # ---- 头程 ----
    logistics_cost: Optional[Decimal] = None
    if logistics_rule is None or logistics_rule.freight_unit_rate is None:
        reasons.append(MISSING_LOGISTICS_RULE)
    else:
        rate = Decimal(str(logistics_rule.freight_unit_rate))
        basis = logistics_rule.billing_basis
        if basis == "volume":
            if unit_volume is None:
                reasons.append(MISSING_UNIT_VOLUME)
            else:
                logistics_cost = _money(unit_volume * rate)
        elif basis == "weight":
            if weight_tier is None:
                reasons.append(MISSING_WEIGHT_TIER)
            else:
                logistics_cost = _money(
                    tier_representative_weight_kg(weight_tier) * rate
                )
        elif basis in {"quantity", "fixed"}:
            logistics_cost = _money(rate)
        else:
            # 未知计费方式 ⇒ 不猜，宁可不算。
            reasons.append(MISSING_LOGISTICS_RULE)

    # ---- 仓储 ----
    storage_cost: Optional[Decimal] = None
    if storage_rule is None:
        reasons.append(MISSING_STORAGE_RULE)
    elif unit_volume is None:
        reasons.append(MISSING_UNIT_VOLUME)
    elif reference_storage_days(turnover_class) is None:
        reasons.append(MISSING_TURNOVER_CLASS)
    else:
        storage_cost = build_reference_storage_cost(
            unit_volume_cbm=unit_volume,
            unit_rate_cny_per_cbm_month=storage_rule.unit_rate_cny,
            turnover_class=turnover_class,
        )

    # ---- 贴单 ----
    # 仓储规则**没配**贴单费 ⇒ 按 0（与利润链 ``assumed_zero`` 同口径：
    # 贴单是可选成本项，没配就是这项不要钱）。
    # 但仓储规则**整个没有** ⇒ 贴单也算不出来 ⇒ 未计入。
    if storage_rule is None:
        label_fee: Optional[Decimal] = None
    elif storage_rule.label_fee is None:
        label_fee = Decimal("0")
    else:
        label_fee = Decimal(str(storage_rule.label_fee))

    return {
        "logistics_cost": logistics_cost,
        "storage_cost": storage_cost,
        "label_fee": label_fee,
        "missing_reasons": list(dict.fromkeys(reasons)),
    }


async def _load_warehouse_logistics_rule(db: AsyncSession, warehouse_code: str):
    """该仓**不限运输方式**时唯一可确定的头程规则；挑不出来就是 ``None``。"""
    statement = select(LogisticsProviderRule).where(
        or_(
            LogisticsProviderRule.warehouse_code == warehouse_code,
            LogisticsProviderRule.warehouse_code.is_(None),
        ),
        LogisticsProviderRule.status == "active",
        LogisticsProviderRule.is_sensitive.is_(False),
        LogisticsProviderRule.currency == "CNY",
        LogisticsProviderRule.effective_from <= date.today(),
        (LogisticsProviderRule.effective_to.is_(None))
        | (LogisticsProviderRule.effective_to >= date.today()),
    )
    rules = (await db.execute(statement)).scalars().all()
    return select_logistics_rule(rules, warehouse_code)


async def _load_warehouse_storage_rule(db: AsyncSession, warehouse_code: str):
    statement = (
        select(WarehouseStorageRule)
        .where(
            WarehouseStorageRule.warehouse_code == warehouse_code,
            WarehouseStorageRule.status == "active",
            WarehouseStorageRule.effective_from <= date.today(),
            (WarehouseStorageRule.effective_to.is_(None))
            | (WarehouseStorageRule.effective_to >= date.today()),
        )
        .order_by(
            WarehouseStorageRule.effective_from.desc(),
            WarehouseStorageRule.rule_id.desc(),
        )
    )
    return (await db.execute(statement)).scalars().first()


async def _load_weight_tiers(db: AsyncSession) -> dict[str, DimWeightTier]:
    """重量段是**全局一套**（``core.dim_weight_tiers``）⇒ 一次读进内存。"""
    rows = (await db.execute(select(DimWeightTier))).scalars().all()
    return {row.tier_code: row for row in rows}


async def load_fulfillment_costs(
    db: AsyncSession,
    sku_rows: Iterable[DimErpSku],
    warehouse_code: Optional[str],
) -> dict[int, dict]:
    """批量算每个 SKU 的履约按件成本（头程 / 仓储 / 贴单）。

    返回 ``{sku_id: {"logistics_cost", "storage_cost", "label_fee", "missing_reasons"}}``。

    ⚠️ **没选仓** ⇒ 拿不到仓级规则 ⇒ 三项全部「未计入」+
    ``missing_warehouse_for_fulfillment``：与尾程不传仓就不进底线是同一套纪律
    —— 不同仓的头程/仓储/贴单不一样，不指定仓却给一个数 = 偷用一个运营没选的仓。
    """
    rows = list(sku_rows)
    if not rows:
        return {}
    if not warehouse_code:
        return {
            row.sku_id: {
                "logistics_cost": None,
                "storage_cost": None,
                "label_fee": None,
                "missing_reasons": [MISSING_WAREHOUSE],
            }
            for row in rows
        }

    logistics_rule = await _load_warehouse_logistics_rule(db, warehouse_code)
    storage_rule = await _load_warehouse_storage_rule(db, warehouse_code)
    tiers = await _load_weight_tiers(db)
    out: dict[int, dict] = {}
    for row in rows:
        out[row.sku_id] = compute_fulfillment_costs(
            unit_volume=unit_volume_cbm(row),
            turnover_class=row.turnover_class,
            logistics_rule=logistics_rule,
            storage_rule=storage_rule,
            weight_tier=(
                tiers.get(row.weight_tier_code) if row.weight_tier_code else None
            ),
        )
    return out
