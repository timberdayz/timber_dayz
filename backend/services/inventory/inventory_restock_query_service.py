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

仓级取数（阶段 6）
------------------
``load_restock_days_by_warehouse`` 给出**每个仓各自**的库龄，
供「这个 SKU 在新加坡仓滞销、在马来仓不滞销」这类判断使用。

⚠️ **两个函数的过滤条件必须逐字对齐**（都是 ``available_stock > 0``）：
已经清空的仓不压资金，不参与天数统计。两者一旦分叉，
商品中心会给出两个答案 —— 这是口径纪律最忌讳的事。

（阶段 7 起另有一个 ``inventory_warehouse_stock_query_service`` 专门取**库存数量**，
它**刻意不继承** ``available_stock > 0`` —— 零库存行正是"已清仓"这条事实本身。
那条路只出数量、不参与档位与底线，两条口径互不干扰。）

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


# 仓级：每仓各自算（同样只算有库存的仓）
_RESTOCK_BY_WAREHOUSE_STMT = text(
    "SELECT sku_key, "
    "warehouse_name, "
    "warehouse_code, "
    "MAX(CURRENT_DATE - stock_added_at::date) AS days_since_restock, "
    "SUM(available_stock) AS current_qty, "
    "SUM(inventory_value) AS inventory_value "
    "FROM mart.inventory_state "
    "WHERE sku_key IN :keys AND available_stock > 0 "
    "GROUP BY sku_key, warehouse_name, warehouse_code"
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

    key_to_sku = await load_sku_key_map(db, sku_ids)
    if not key_to_sku:
        return {}

    try:
        async with db.begin_nested():
            exists = (
                await db.execute(text("SELECT to_regclass('mart.inventory_state')"))
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


async def load_restock_days_by_warehouse(
    db: AsyncSession, sku_ids: list[int]
) -> dict[int, dict[str, dict]]:
    """按仓取「距上次进货天数」—— **每个仓各自算**。

    返回 ``{sku_id: {warehouse_key: {...}}}``，其中 ``warehouse_key`` 优先用
    规范仓代码 ``warehouse_code``；**归一不出来的仓**（``warehouse_code`` 为空）
    用原始仓名兜底当键 —— 这样这类仓既不会混进别的仓，也不会凭空消失。

    每项内容与 SKU 级那一份**同名字段**：
    ``days_since_restock`` / ``current_qty`` / ``inventory_value``，
    外加 ``warehouse_name``（原始仓名，页面要显示）与 ``warehouse_code``。

    ⚠️ 过滤条件与 ``load_current_restock_days`` **逐字对齐**
    （``available_stock > 0``）：已清空的仓不压资金，不参与。
    """
    if not sku_ids:
        return {}

    key_to_sku = await load_sku_key_map(db, sku_ids)
    if not key_to_sku:
        return {}

    try:
        async with db.begin_nested():
            exists = (
                await db.execute(text("SELECT to_regclass('mart.inventory_state')"))
            ).scalar()
            if not exists:
                return {}
            rows = (
                await db.execute(
                    _RESTOCK_BY_WAREHOUSE_STMT,
                    {"keys": list(key_to_sku)},
                )
            ).all()
    except Exception as exc:  # noqa: BLE001
        from modules.core.logger import get_logger

        get_logger(__name__).warning(
            "inventory restock days by warehouse lookup failed: %s", exc
        )
        return {}

    result: dict[int, dict[str, dict]] = {}
    for row in rows:
        sku_id = key_to_sku.get(row.sku_key)
        if sku_id is None:
            continue
        warehouse_name = row.warehouse_name or ""
        warehouse_code = row.warehouse_code
        # 归一不出来的仓用原始仓名兜底当键：不混进别的仓，也不凭空消失
        warehouse_key = warehouse_code or warehouse_name
        if not warehouse_key:
            continue
        result.setdefault(sku_id, {})[warehouse_key] = {
            "warehouse_code": warehouse_code,
            "warehouse_name": warehouse_name,
            "days_since_restock": (
                int(row.days_since_restock)
                if row.days_since_restock is not None
                else None
            ),
            "current_qty": int(row.current_qty or 0),
            "inventory_value": float(row.inventory_value or 0.0),
        }
    return result


async def load_sku_key_map(db: AsyncSession, sku_ids: list[int]) -> dict[str, int]:
    """``{sku_key: sku_id}`` —— ERP 主数据里的商品键到内部 id 的映射。

    ⚠️ **用 sku_key 查，不是 sku_id**：ERP 编号（用户口中的"商品号"）是
    ``sku_key``（字符串），``sku_id`` 是内部整数主键。拿整数去查字符串列会静默返回空。

    （库存快照那条路也要这个映射，所以它是**公开**的。）
    """
    rows = (
        await db.execute(
            select(DimErpSku.sku_id, DimErpSku.sku_key).where(
                DimErpSku.sku_id.in_(sku_ids)
            )
        )
    ).all()
    return {row.sku_key: row.sku_id for row in rows}


async def probe_inventory_state_available(db: AsyncSession) -> bool:
    """状态层（``mart.inventory_state``）在不在、查不查得动。

    为什么要单独探一次
    ------------------
    ``load_current_restock_days`` 返回空，只有两种可能：
    (a) 状态层表不存在 / 查询失败 —— **管道坏了**；
    (b) 表在，但**这批 SKU 在状态层里没有有库存的记录** —— 业务事实，不是故障。

    这两件事以前只能靠一句 ``inventory_state unavailable`` 混着报，
    于是"这批货都清空了"每次都被报成"系统不可用"—— **误报告警**。
    有了这个探测，调用方才能把两者分开说。

    实现：用一句最轻的查询探活，**不**用 ``to_regclass``（那是 PostgreSQL 专有，
    SQLite 测试环境下会直接抛异常，反而把"表在"说成"不在"）。
    """
    try:
        async with db.begin_nested():
            await db.execute(text("SELECT 1 FROM mart.inventory_state LIMIT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False
