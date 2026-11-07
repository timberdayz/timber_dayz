"""距上次进货天数（Days Since Last Restock）—— **唯一实现**。

业务定义
--------
西虹的经营模式：**卖完不补货，偶尔补货**。
所以「库龄」在业务上 = **距上次进货的时间**，**补货即重置**。

实测依据（两批快照对比 1109 个共同 SKU×仓）
------------------------------------------
- 妙手「创建时间」= **首次铺货时间**，补货**不会**重置它（1109/1109 行不变）
- 妙手「更新时间」**每次写入都变**，连销售都会变（0/1109 行相同）
- 可用库存与库存总量变化方向 100% 一致；总量多捕捉 2 行（预占变化）

→ 两者都不能直接当计时器 → 必须自己维护「上次进货时间」= ``stock_added_at``。

分档门槛
--------
与商品中心档位表（``finance.sku_pricing_policies``）的 0/60/90/120 天**同源**，
这样滞销榜和商品中心不会自相矛盾（「榜上说不滞销、价格却按滞销打」）。

本模块是**纯函数**：无 ORM、无 DB、无 I/O，可写无 DB 单测。
滞销模块与商品中心都调它（唯一实现纪律）。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Optional

# 分档（升序门槛，与商品中心档位表一致）
RESTOCK_TIER_UNKNOWN = "unknown"
RESTOCK_TIER_ACTIVE = "active"
RESTOCK_TIER_LIGHT = "light"
RESTOCK_TIER_MID = "mid"
RESTOCK_TIER_DEEP = "deep"

# 门槛（天）。第一个门槛以下 = 活跃；最后一个门槛以上 = 重度（公司要想办法清理）。
RESTOCK_TIER_THRESHOLDS: tuple[int, ...] = (60, 90, 120)

RESTOCK_TIER_LABELS: dict[str, str] = {
    RESTOCK_TIER_UNKNOWN: "不可算",
    RESTOCK_TIER_ACTIVE: "活跃",
    RESTOCK_TIER_LIGHT: "压60-90天",
    RESTOCK_TIER_MID: "压90-120天",
    RESTOCK_TIER_DEEP: "压120天以上",
}

# 进滞销榜的档位（≥ 第一个门槛）
RESTOCK_BACKLOG_TIERS = (RESTOCK_TIER_LIGHT, RESTOCK_TIER_MID, RESTOCK_TIER_DEEP)

#: 档位 key 的固定顺序（汇总分组、图表渲染都按这个顺序）。
RESTOCK_TIER_ORDER: tuple[str, ...] = (
    RESTOCK_TIER_ACTIVE,
    RESTOCK_TIER_LIGHT,
    RESTOCK_TIER_MID,
    RESTOCK_TIER_DEEP,
)

#: 业务定价档位表（``finance.sku_pricing_policies``）的门槛序列：
#: 基础档 0 + 三个滞销门槛。**必须与 ``RESTOCK_TIER_THRESHOLDS`` 同源**。
RESTOCK_POLICY_THRESHOLDS: tuple[int, ...] = (0,) + RESTOCK_TIER_THRESHOLDS

#: 旧标准指标「深度积压」的天数门槛（指标词典口径，**不改**）。
#:
#: 它是「压在仓里多久算深度积压」这一**独立指标**，
#: 与档位分组（0/60/90/120）是两回事：档位回答「该打几折」，
#: 深度积压回答「压了多久没动」。两个都留着，互不替代。
DEEP_STAGNANT_MIN_DAYS = 180

#: 旧标准指标「中度积压」的天数门槛（指标词典口径，**不改**）。
MID_STAGNANT_MIN_DAYS = 90


def _to_date(value) -> Optional[date]:
    """把 date / datetime 统一成 date；无法识别返回 None。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def compute_days_since_restock(*, stock_added_at, as_of) -> Optional[int]:
    """距上次进货天数 = as_of − stock_added_at（自然日）。

    ``stock_added_at`` 是「库存总量最后一次**增加**（进货）的时间」，
    由落盘层的行内容 diff 维护（**不是**妙手的「更新时间」——那个连销售都会变）。
    取不到基准时间返回 None。
    """
    added = _to_date(stock_added_at)
    today = _to_date(as_of)
    if added is None or today is None:
        return None
    return max((today - added).days, 0)


def classify_restock_tier(
    days: Optional[int],
    thresholds: Iterable[int] = RESTOCK_TIER_THRESHOLDS,
) -> str:
    """按「距上次进货天数」分档。不可算单独一档，**不得回落「活跃」**。

    回落「活跃」会让「算不出」被当成「最新鲜」——最该降价的反而拿最低折扣。
    """
    if days is None:
        return RESTOCK_TIER_UNKNOWN
    bounds = sorted(int(t) for t in thresholds)
    if not bounds:
        return RESTOCK_TIER_ACTIVE
    tier_by_index = (RESTOCK_TIER_LIGHT, RESTOCK_TIER_MID, RESTOCK_TIER_DEEP)
    hit = RESTOCK_TIER_ACTIVE
    for index, bound in enumerate(bounds):
        if days >= bound:
            hit = tier_by_index[min(index, len(tier_by_index) - 1)]
    return hit


def restock_tier_key_for_threshold(
    threshold: int,
    thresholds: Iterable[int] = RESTOCK_TIER_THRESHOLDS,
) -> str:
    """把「业务定价档位表的门槛」翻译成档位 key。

    门槛序列 = 基础档 0 + 滞销门槛（60 / 90 / 120），与
    ``finance.sku_pricing_policies`` 的当前生效行一一对应。

    门槛对不上唯一实现 ⇒ **抛错**（不静默猜一个档位）：
    业务改了档位表却没同步这里，必须立刻暴露，而不是悄悄算错。
    """
    bounds = sorted(int(t) for t in thresholds)
    policy_thresholds = [0] + bounds
    keys = (
        RESTOCK_TIER_ACTIVE,
        RESTOCK_TIER_LIGHT,
        RESTOCK_TIER_MID,
        RESTOCK_TIER_DEEP,
    )
    if len(policy_thresholds) != len(keys):
        raise ValueError(
            f"档位门槛数量对不上：thresholds={bounds} ⇒ policy={policy_thresholds}，"
            f"但档位 key 只有 {len(keys)} 个"
        )
    try:
        index = policy_thresholds.index(int(threshold))
    except ValueError:
        raise ValueError(
            f"档位门槛 {threshold} 与唯一实现 {policy_thresholds} 对不上 —— "
            f"业务定价档位表改了，必须同步 RESTOCK_TIER_THRESHOLDS"
        )
    return keys[index]


def build_restock_tier_buckets(
    rows: Iterable[dict],
    thresholds: Iterable[int] = RESTOCK_TIER_THRESHOLDS,
) -> dict:
    """按**业务定价档位**分组汇总（互斥 4 档，SKU 级）。

    为什么是 SKU 级
    --------------
    商品中心的定价是 **SKU 级**（一个仓压着没补货，就是这货整体压着），
    所以档位必须按 SKU 算：库龄 = 各仓**最长**（只算还有可售库存的仓），
    货值 = 该 SKU 全部仓的货值之和 ⇒ SKU 数与货值都**互斥可加**
    （加起来正好等于总数，不会出现「各档加起来比总数多」）。

    为什么是「唯一实现」
    ------------------
    行级明细的档位是 ``classify_restock_tier`` 算出来的；汇总如果另写一套
    阈值判据，就会出现「明细说 60~90、汇总说活跃」这种自相矛盾。
    所以汇总**逐 SKU 调用同一套函数** ⇒ 汇总与明细永远对得上。

    返回
    ----
    ``{"buckets": [...], "total_value": ..., "total_quantity": ...,
    "total_row_count": ..., "total_sku_count": ..., "unknown_row_count": ...}``

    每个 bucket：``{tier, label, threshold_days, value, row_count, sku_count}``。
    """
    bounds = sorted(int(t) for t in thresholds)

    # SKU 级聚合：库龄 = 各仓最长（只算还有可售库存的仓）
    sku_rows: dict[tuple[str, str], list[dict]] = {}
    total_value = 0.0
    total_quantity = 0.0
    total_row_count = 0
    for row in rows:
        value = _to_float_or_zero(row.get("inventory_value"))
        total_value += value
        total_quantity += _to_float_or_zero(row.get("available_stock"))
        total_row_count += 1
        key = (
            str(row.get("platform_code") or ""),
            str(row.get("product_sku") or ""),
        )
        sku_rows.setdefault(key, []).append(row)

    tier_of_sku: dict[str, dict] = {
        tier: {
            "tier": tier,
            "label": RESTOCK_TIER_LABELS[tier],
            "threshold_days": threshold,
            "value": 0.0,
            "row_count": 0,
            "sku_count": 0,
        }
        for tier, threshold in zip(RESTOCK_TIER_ORDER, RESTOCK_POLICY_THRESHOLDS)
    }

    unknown_row_count = 0
    unknown_sku_count = 0
    for group in sku_rows.values():
        sku_days = aggregate_sku_restock_days(group)
        tier = classify_restock_tier(sku_days, thresholds=bounds)
        sku_value = sum(_to_float_or_zero(row.get("inventory_value")) for row in group)
        if tier == RESTOCK_TIER_UNKNOWN:
            # 「算不出库龄」**不得**回落活跃 —— 单独计数，让缺失在数据上可见。
            unknown_row_count += len(group)
            unknown_sku_count += 1
            continue
        bucket = tier_of_sku[tier]
        bucket["value"] += sku_value
        bucket["row_count"] += len(group)
        bucket["sku_count"] += 1

    buckets = []
    for tier in RESTOCK_TIER_ORDER:
        bucket = tier_of_sku[tier]
        buckets.append(
            {
                "tier": tier,
                "label": bucket["label"],
                "threshold_days": bucket["threshold_days"],
                "value": round(float(bucket["value"]), 2),
                "row_count": int(bucket["row_count"]),
                "sku_count": int(bucket["sku_count"]),
            }
        )

    return {
        "buckets": buckets,
        "total_value": round(total_value, 2),
        "total_quantity": int(total_quantity),
        "total_row_count": int(total_row_count),
        "total_sku_count": len(sku_rows),
        "unknown_row_count": int(unknown_row_count),
        "unknown_sku_count": int(unknown_sku_count),
    }


def normalize_policy_tier_buckets(
    policy_tiers: Iterable[dict],
    thresholds: Iterable[int] = RESTOCK_TIER_THRESHOLDS,
) -> list[dict]:
    """把「SQL 视图给的档位分组」归一化成与 Python 汇总**同构**的 bucket 列表。

    为什么需要它
    ------------
    SQL 视图从 ``finance.sku_pricing_policies`` 读门槛（动态、改档位表自动跟随），
    Python 侧有唯一实现 ``RESTOCK_TIER_THRESHOLDS``。两边必须对齐，
    对不上就**抛错**（不静默猜一个档位）。

    SQL 侧的 tier_label 是业务表的显示名（日常 / 库龄≥60天 / …），
    这里统一换成 Python 侧的档位名（活跃 / 压60-90天 / …），
    这样看板各处的文案是同一套。
    """
    buckets: dict[str, dict] = {}
    for item in policy_tiers or []:
        threshold = item.get("min_restock_days")
        if threshold is None:
            raise ValueError(f"档位分组缺少门槛：{item!r}")
        tier = restock_tier_key_for_threshold(int(threshold), thresholds)
        buckets[tier] = {
            "tier": tier,
            "label": RESTOCK_TIER_LABELS[tier],
            "threshold_days": int(threshold),
            "value": round(_to_float_or_zero(item.get("inventory_value")), 2),
            "row_count": int(_to_float_or_zero(item.get("row_count"))),
            "sku_count": int(_to_float_or_zero(item.get("sku_count"))),
        }

    missing = [tier for tier in RESTOCK_TIER_ORDER if tier not in buckets]
    if missing:
        raise ValueError(
            f"档位分组缺少档位 {missing} —— 业务定价档位表与唯一实现对不上，"
            f"必须同步 RESTOCK_TIER_THRESHOLDS"
        )
    return [buckets[tier] for tier in RESTOCK_TIER_ORDER]


def _to_float_or_zero(value) -> float:
    """把可能是 ``None`` / 字符串的值转成 ``float``；转不了按 0 算。"""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def has_stock(row: dict) -> bool:
    """该行是否还有可售库存。"""
    available = row.get("available_stock")
    if available is None:
        return False
    try:
        return float(available) > 0
    except (TypeError, ValueError):
        return False


def aggregate_sku_restock_days(rows: Iterable[dict]) -> Optional[int]:
    """SKU 级聚合：**取各仓最长**（只算还有库存的仓）。

    商品中心是 SKU 级定价（全国一价）；一个仓压着没补货，就是这货整体压着。
    全都不可算时返回 None（→ 档位 `unknown`，不得回落日常档）。
    """
    values = [
        row["days_since_restock"]
        for row in rows
        if row.get("days_since_restock") is not None and has_stock(row)
    ]
    return max(values) if values else None


def aggregate_sku_restock_tier(
    rows: Iterable[dict],
    thresholds: Iterable[int] = RESTOCK_TIER_THRESHOLDS,
) -> str:
    """SKU 级档位：先聚合天数再分档。"""
    return classify_restock_tier(
        aggregate_sku_restock_days(rows), thresholds=thresholds
    )


def build_restock_row(
    *,
    platform_code: str,
    sku_key: str,
    warehouse_name: str,
    stock_added_at,
    as_of,
    available_stock,
    thresholds: Iterable[int] = RESTOCK_TIER_THRESHOLDS,
) -> dict:
    """组装一行仓级「距上次进货」记录（纯函数，供服务层与测试共用）。"""
    days = compute_days_since_restock(stock_added_at=stock_added_at, as_of=as_of)
    return {
        "platform_code": platform_code,
        "sku_key": sku_key,
        "warehouse_name": warehouse_name,
        "available_stock": available_stock,
        "stock_added_at": stock_added_at,
        "days_since_restock": days,
        "restock_tier": classify_restock_tier(days, thresholds=thresholds),
    }
