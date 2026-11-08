"""跨仓差异判定 —— 「优先调拨，而非降价」。

业务问题
--------
同一个 ERP SKU 可能在两个仓都有货：
新加坡仓刚补过货（库龄 10 天），马来仓压了半年（库龄 150 天）。

这时候**降价是错的动作**：
马来仓滞销说明的是**马来仓**的货压住了，而新加坡站点的货是新鲜的、卖得动的。
正确的动作是**把货从马来仓调拨到新加坡**（或者调拨到马来站去清），
而不是把**整个 SKU 在所有站点的底线**都压下去 —— 那会让新加坡站本来
卖得动的货也贱卖了。

⚠️ 所以本模块**只判定、只提示，不改价、不自动调价**：
调拨是运营决策，系统不越权；底线该多少还是多少。

判定口径
--------
**跨仓差异 = 同一 SKU 在 ≥2 个仓有库存，且这些仓命中的库龄档位不同。**

为什么用「档位不同」而不是「天数差 ≥ N」
--------------------------------------
档位就是**底线真正跟着变的那条线**（折扣率与目标利润率都按档位走）。
两个仓天数差 5 天但都落在同一档 ⇒ 底线一样 ⇒ 没有差异可提示。
两个仓天数差 70 天且分属两档 ⇒ 底线不同 ⇒ **确实存在"该调拨不该降价"的差异**。

⚠️ 档位门槛来自规则表（生产：0/60/90/120 天），**不在这里写死** ——
规则表改了，这里的判定自动跟着改。

纯函数
------
本模块**不碰数据库、不读文件**：入参是「每仓库龄」和「规则档位」，
出参是判定结果。这样它能写成无 DB 单测 —— 业务判断只有这一处实现。
"""

from __future__ import annotations

from typing import Iterable, Optional

from backend.services.product_pricing_service import select_restock_tier


#: 判定跨仓差异时，**至少要有几个仓**才有意义。
#: 一个仓谈不上「跨仓」；零个仓是数据缺失，不是差异。
MIN_WAREHOUSES = 2


def detect_warehouse_divergence(
    warehouse_restocks: dict[str, dict],
    policies: Iterable[dict],
) -> Optional[dict]:
    """判定同一个 SKU 在各仓之间是否存在库龄档位差异。

    入参 ``warehouse_restocks``：``{warehouse_key: {...}}``，
    每项需含 ``days_since_restock``（可为空）与 ``warehouse_name`` /
    ``warehouse_code``（用于展示）。

    返回 ``None`` 表示**没有差异**；有差异时返回：

    - ``warehouse_count``：参与判定的仓数
    - ``stagnant_warehouses``：命中**最深档**（最滞销）的仓列表
    - ``fresh_warehouses``：命中**最浅档**（最不滞销）的仓列表
    - ``min_days`` / ``max_days``：各仓库龄的最小/最大值
    - ``suggestion``：给运营的一句话建议（**调拨，不是降价**）

    ⚠️ **只算还有库存的仓**：已经清空的仓不压资金，不参与。
    取数层（``load_restock_days_by_warehouse``）已经过滤掉 ``available_stock = 0``
    的仓，这里再做一次防御性过滤 —— 纯函数可能被别处直接调用。
    """
    rows = [
        row
        for row in (warehouse_restocks or {}).values()
        if row and ((row.get("current_qty") or 0) > 0)
    ]
    if len(rows) < MIN_WAREHOUSES:
        return None

    policy_rows = [p for p in policies if p is not None]
    if not policy_rows:
        return None

    # 每个仓命中哪一档 —— 用**同一个** ``select_restock_tier``，与底线计算完全一致。
    # ⚠️ 这里如果自己写一套档位判定，就会出现「提示说的档位」和「底线用的档位」对不上。
    tiered: list[tuple[dict, dict, Optional[int]]] = []
    for row in rows:
        days = row.get("days_since_restock")
        tiered.append((row, select_restock_tier(policy_rows, days), days))
    if len(tiered) < MIN_WAREHOUSES:
        return None

    tier_starts = [
        tier["min_restock_days"] for _row, tier, _days in tiered if tier is not None
    ]
    if not tier_starts:
        return None

    deepest_start = max(tier_starts)
    shallowest_start = min(tier_starts)
    # 全都落在同一档 ⇒ 没有差异可提示
    if deepest_start == shallowest_start:
        return None

    stagnant = [
        _warehouse_brief(row, tier, days)
        for row, tier, days in tiered
        if tier is not None and tier["min_restock_days"] == deepest_start
    ]
    fresh = [
        _warehouse_brief(row, tier, days)
        for row, tier, days in tiered
        if tier is not None and tier["min_restock_days"] == shallowest_start
    ]
    day_values = [days for _row, _tier, days in tiered if days is not None]

    stagnant_names = "、".join(item["warehouse_name"] for item in stagnant)
    fresh_names = "、".join(item["warehouse_name"] for item in fresh)

    return {
        "warehouse_count": len(tiered),
        "stagnant_warehouses": stagnant,
        "fresh_warehouses": fresh,
        "min_days": min(day_values) if day_values else None,
        "max_days": max(day_values) if day_values else None,
        "suggestion": (
            f"{stagnant_names} 的库龄已跨到滞销档，"
            f"而 {fresh_names} 仍是正常周转。"
            "建议优先把滞销仓的库存调拨到正常周转的站点去消化，"
            "而不是压低全站点底线。"
        ),
    }


def _warehouse_brief(row: dict, tier: Optional[dict], days: Optional[int]) -> dict:
    """一个仓的摘要：给页面显示用。"""
    return {
        "warehouse_code": row.get("warehouse_code"),
        "warehouse_name": row.get("warehouse_name") or row.get("warehouse_code") or "",
        "days_since_restock": days,
        "tier_label": tier.get("tier_label") if tier else None,
        "current_qty": row.get("current_qty"),
        "inventory_value": row.get("inventory_value"),
    }
