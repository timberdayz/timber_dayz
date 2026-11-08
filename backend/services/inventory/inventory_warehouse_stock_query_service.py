"""当前仓的**库存数量**快照 —— 与「库龄（距上次进货天数）」**分家**的一条口径。

为什么必须分家
--------------
业务上这是两件事：

- **库龄**：这批货压了多久 ⇒ 只看**还有库存**的仓（已清空的仓不压资金，不参与）
- **库存数量**：这个仓现在**还剩多少货** ⇒ **零库存的行也要列出来**
  （「零」本身就是事实：它说明这仓已经清空，而不是「数据没采到」）

混在一条口径里，后果是运营在测算表上看到「库龄 - 天」，
分不清是「这仓压了 90 天」还是「这仓早清空了、压根没货」——
于是把清仓的 SKU 当成滞销品去降价。阶段 7 起，测算表的「当前仓库存」列走本模块，
而库龄 / 档位 / 底线**一个字都不改**（仍在 ``inventory_restock_query_service``）。

本模块的纪律
------------
1. **只取数量**，不参与档位判定、不影响底线计算 —— 它是"事实展示"，不是"定价输入"；
2. 库龄那条路的过滤条件（``available_stock > 0``）在这里**一个字都不继承**：
   本模块要的就是把零库存也捞出来；
3. 容错照旧：表不存在 / 查询失败 ⇒ 返回「状态层不可用」并留日志，
   **绝不静默返回空**（空 = 全部已清仓，是会被误读成事实的）。

数据来源
--------
``mart.inventory_state``（每 SKU×仓 一行，采集侧持续 upsert）：
``available_stock``（可用库存）/ ``on_hand_stock``（在库）/ ``reserved_stock``（预留）/
``inventory_value``（库存金额）。

⚠️ 用 ``sku_key`` 关联，不是 ``sku_id``：ERP 编号（用户口中的"商品号"）是字符串
``sku_key``，``sku_id`` 是内部整数主键，拿整数去查字符串列会静默返回空。
"""

from __future__ import annotations

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from .inventory_restock_query_service import (
    load_sku_key_map,
    probe_inventory_state_available,
)

#: 当前仓的库存快照 —— **含零库存行**。
#:
#: ⚠️ 这里**没有** ``available_stock > 0``，与库龄那条路刻意不同：
#: 零库存行就是「这个仓已经清空」这条事实本身，必须带出来。
_WAREHOUSE_STOCK_STMT = text(
    "SELECT sku_key, "
    "warehouse_name, "
    "warehouse_code, "
    "SUM(available_stock) AS available_stock, "
    "SUM(on_hand_stock) AS on_hand_stock, "
    "SUM(reserved_stock) AS reserved_stock, "
    "SUM(inventory_value) AS inventory_value "
    "FROM mart.inventory_state "
    "WHERE sku_key IN :keys AND warehouse_code = :warehouse_code "
    "GROUP BY sku_key, warehouse_name, warehouse_code"
).bindparams(bindparam("keys", expanding=True))


#: 库存状态取值（写进接口返回，前端据此显示文案）
STOCK_STATUS_IN_STOCK = "in_stock"
"""当前仓还有可用库存 —— 在卖。"""

STOCK_STATUS_CLEARED = "cleared"
"""当前仓有这条库存记录，但可用库存为 0 —— 已清空。"""

STOCK_STATUS_NO_RECORD = "no_record"
"""状态层里没有这个 SKU 在当前仓的任何记录 —— 这个仓压根没有它的货。"""

STOCK_STATUS_UNAVAILABLE = "unavailable"
"""状态层不可用（表不存在 / 查询失败）—— 取不到，不是「没有货」。"""


async def load_warehouse_stock_snapshot(
    db: AsyncSession, sku_ids: list[int], warehouse_code: str
) -> dict:
    """当前仓的库存数量快照（**含零库存行**）。

    返回::

        {
            "available": bool,          # 状态层是否可用（False = 表不存在 / 查询失败）
            "by_sku": {sku_id: {...}},  # 只包含在当前仓有库存行的 SKU
        }

    ``by_sku`` 的每一项::

        {
            "warehouse_code": str|None,
            "warehouse_name": str,
            "available_stock": int,      # 可用库存
            "on_hand_stock": int,        # 在库数量
            "reserved_stock": int,       # 预留数量
            "inventory_value": float,    # 库存金额
        }

    ⚠️ **状态层不可用时返回空字典 + ``available=False``**，
    调用方必须据此区分「这个仓没有这个货」与「取不到」——
    两者在页面上长得一样，业务含义完全相反。
    """
    result = {"available": False, "by_sku": {}}
    if not sku_ids or not warehouse_code:
        return result

    key_to_sku = await load_sku_key_map(db, sku_ids)
    if not key_to_sku:
        return result

    if not await probe_inventory_state_available(db):
        from modules.core.logger import get_logger

        get_logger(__name__).warning(
            "inventory_state unavailable, warehouse stock snapshot cannot be read"
        )
        return result

    try:
        async with db.begin_nested():
            rows = (
                await db.execute(
                    _WAREHOUSE_STOCK_STMT,
                    {
                        "keys": list(key_to_sku),
                        "warehouse_code": warehouse_code,
                    },
                )
            ).all()
    except Exception as exc:  # noqa: BLE001
        from modules.core.logger import get_logger

        get_logger(__name__).warning(
            "inventory warehouse stock snapshot lookup failed: %s", exc
        )
        return result

    by_sku: dict[int, dict] = {}
    for row in rows:
        sku_id = key_to_sku.get(row.sku_key)
        if sku_id is None:
            continue
        by_sku[sku_id] = {
            "warehouse_code": row.warehouse_code,
            "warehouse_name": row.warehouse_name or "",
            "available_stock": int(row.available_stock or 0),
            "on_hand_stock": int(row.on_hand_stock or 0),
            "reserved_stock": int(row.reserved_stock or 0),
            "inventory_value": float(row.inventory_value or 0.0),
        }
    result["available"] = True
    result["by_sku"] = by_sku
    return result


def resolve_stock_status(stock: dict | None, state_available: bool = True) -> str:
    """把一条库存快照翻译成**页面能直接用**的状态词。

    - 有可用库存 ⇒ ``in_stock``（在卖）
    - 有记录但可用库存为 0 ⇒ ``cleared``（**已清仓** —— 这是一条事实，不是缺数据）
    - 压根没有这条记录 ⇒ ``no_record``（这个仓没有它的货）
    - 状态层不可用 ⇒ ``unavailable``（**取不到**，不能当成「没有货」）
    """
    if not state_available:
        return STOCK_STATUS_UNAVAILABLE
    if not stock:
        return STOCK_STATUS_NO_RECORD
    if int(stock.get("available_stock") or 0) > 0:
        return STOCK_STATUS_IN_STOCK
    return STOCK_STATUS_CLEARED


def select_sku_ids_by_stock(
    candidate_ids: list[int],
    sku_key_by_id: dict[int, str],
    stock_by_sku: dict[int, dict],
    only_in_stock: bool = True,
) -> list[int]:
    """按**当前仓库存**过滤并排序，给出要分页的 sku_id 顺序。

    规则
    ----
    1. **有货优先**：有可用库存的排前面 —— 运营打开测算表先看还有货的；
    2. 组内按 **ERP SKU 升序** —— 顺序稳定，运营翻页习惯不变；
    3. ``only_in_stock=True`` ⇒ 只保留有可用库存的（**在分页之前**做，
       否则前端筛选只会筛当前页，总数对不上、翻页还会漏行）。

    ⚠️ 这是一个**纯函数**：不查库、不改口径，只做"给定输入 ⇒ 给定顺序"。
    """
    in_stock: list[tuple[str, int]] = []
    out_of_stock: list[tuple[str, int]] = []
    for sku_id in candidate_ids:
        stock = stock_by_sku.get(sku_id) or {}
        available = int(stock.get("available_stock") or 0)
        item = (sku_key_by_id.get(sku_id) or "", sku_id)
        if available > 0:
            in_stock.append(item)
        else:
            out_of_stock.append(item)
    in_stock.sort(key=lambda pair: pair[0])
    out_of_stock.sort(key=lambda pair: pair[0])
    ordered = [sku_id for _, sku_id in in_stock]
    if not only_in_stock:
        ordered.extend(sku_id for _, sku_id in out_of_stock)
    return ordered
