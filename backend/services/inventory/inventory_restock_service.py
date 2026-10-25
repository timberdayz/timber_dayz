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
