"""按「距上次进货天数」取数 —— 商品中心与 SKU 级滞销清单的**共享**取数入口。

业务定义
--------
西虹的经营模式：**卖完不补货，偶尔补货**。
所以「库龄」= **距上次进货的时间**：库存数量**增加**（进货）就清零，
没有增加就持续累加天数，到门槛（档位表 0/60/90/120）就用折扣库调整最低售价。

数据来源
--------
``mart.inventory_state``（每 SKU×仓 一行，周采集持续 upsert）：
- ``stock_added_at``：上次库存数量增加（进货）的时间 —— 计时器基准
- ``available_stock`` / ``inventory_value``：当前库存与货值

SKU 级聚合：**各仓取最长**（只算还有库存的仓）——
一个仓压着没补货，这货整体就压着；已经清空的仓不压资金，不参与。

容错（照 ``inventory_age_query_service`` 的纪律）
------------------------------------------------
1. ``to_regclass`` 探测表是否存在 —— 不存在就**根本不发出会失败的查询**，事务毫发无损；
2. 万一查询仍失败，用 ``db.begin_nested()`` 开 SAVEPOINT 包住它，
   异常时只回滚到保存点，外层事务仍然可用；
3. **必须留日志** —— 表不存在、列改名、权限不足、SQL 拼错全部退化成同一种「无数据」，
   不记日志的话管道坏了运维无从发现。
"""

from __future__ import annotations

from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import DimErpSku

# SKU 级：各仓取最长（只算有库存的仓）
_RESTOCK_LOOKUP_STMT = text(
    "SELECT sku_key, "
    "MAX(CURRENT_DATE - stock_added_at::date) AS days_since_restock, "
    "SUM(available_stock) AS current_qty, "
    "SUM(inventory_value) AS inventory_value "
    "FROM mart.inventory_state "
    "WHERE sku_key IN :keys AND available_stock > 0 "
    "GROUP BY sku_key"
).bindparams(bindparam("keys", expanding=True))


async def load_current_restock_days(
    db: AsyncSession, sku_ids: list[int]
) -> dict[int, dict]:
    """按 product_sku -> dim_erp_sku.sku_key 关联取「距上次进货天数」与库存快照。

    返回 ``{sku_id: {"days_since_restock": int|None, "current_qty": int,
    "inventory_value": float}}``，**只包含状态层里出现过的 SKU**。
    """
    if not sku_ids:
        return {}

    rows = (
        await db.execute(
            select(DimErpSku.sku_id, DimErpSku.sku_key).where(
                DimErpSku.sku_id.in_(sku_ids)
            )
        )
    ).all()
    key_to_sku = {row.sku_key: row.sku_id for row in rows}
    if not key_to_sku:
        return {}

    try:
        async with db.begin_nested():
            exists = (
                await db.execute(
                    text("SELECT to_regclass('mart.inventory_state')")
                )
            ).scalar()
            if not exists:
                # mart 层不存在：不发出会失败的查询，事务保持健康
                return {}
            restock_rows = (
                await db.execute(
                    _RESTOCK_LOOKUP_STMT,
                    {"keys": list(key_to_sku)},
                )
            ).all()
    except Exception as exc:  # noqa: BLE001
        from modules.core.logger import get_logger

        get_logger(__name__).warning(
            "inventory restock days lookup failed, falling back to the base tier: %s",
            exc,
        )
        return {}

    result: dict[int, dict] = {}
    for row in restock_rows:
        sku_id = key_to_sku.get(row.sku_key)
        if sku_id is None:
            continue
        result[sku_id] = {
            "days_since_restock": (
                int(row.days_since_restock)
                if row.days_since_restock is not None
                else None
            ),
            "current_qty": int(row.current_qty or 0),
            "inventory_value": float(row.inventory_value or 0.0),
        }
    return result
