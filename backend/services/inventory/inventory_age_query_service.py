"""当前库龄 / 库存快照的**共享**读取入口。

商品中心（展示最低售价）与最低售价变更通知（判断"要不要通知"）必须读**同一个**库龄口径。
取数一旦分叉成两份，就会出现「商品中心按日常档显示、通知却按滞销档发」的自相矛盾——
这是评审时最容易被忽略、但业务上最伤的一种 bug。所以取数函数放在这里，两边都调它。

口径沿用商品中心既有实现（`product_center._load_age_days_by_sku`）：

- 关联方式：``mart.inventory_age_current.product_sku`` -> ``core.dim_erp_sku.sku_key``
  （mart 侧的 ``sku_id`` 是 varchar 的平台侧 id，与 dim 侧的 integer sku_id 不是一回事）
- 库龄聚合：同一 ``product_sku`` 跨平台取 ``MIN(age_days)``（跨平台取最小 = 最保守）
- 库存聚合：同一 ``product_sku`` 跨平台 ``SUM``
- **只返回在库龄表里出现过的 SKU**：没出现的表示该 SKU 当前没有库存快照
  （已清空 / 未匹配主数据），调用方据此判断「库龄缺失 → 回落第 1 档」
"""

from __future__ import annotations

from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import DimErpSku

# 库龄查询用**展开式绑定参数**（expanding=True），不用 `= ANY(:keys)`。
# 原因：`ANY($1)` 在 asyncpg 下要求驱动能推断出数组类型，
# 而 `text()` 没有类型信息，可能直接报「could not determine data type of parameter」，
# 然后被 `except Exception` 静默吞掉——库龄永远回落「日常」档且**没有任何报错**。
# expanding=True 会渲染成 `IN (?, ?, ...)`，逐个绑定字符串，asyncpg 无需推断数组类型。
_AGE_LOOKUP_STMT = text(
    "SELECT product_sku, "
    "MIN(age_days) AS age_days, "
    "SUM(current_qty) AS current_qty, "
    "SUM(inventory_value) AS inventory_value "
    "FROM mart.inventory_age_current "
    "WHERE product_sku IN :keys "
    "GROUP BY product_sku"
).bindparams(bindparam("keys", expanding=True))


async def load_current_inventory_ages(
    db: AsyncSession, sku_ids: list[int]
) -> dict[int, dict]:
    """按 product_sku -> dim_erp_sku.sku_key 关联取当前库龄与库存快照。

    返回 ``{sku_id: {"age_days": int, "current_qty": int, "inventory_value": float}}``，
    **只包含在库龄表里出现过的 SKU**。

    ⚠️ 必须容错：mart 是 raw SQL 层（sql/mart/*.sql），不在 Base.metadata 里。
    测试库的 conftest 只建 core/a_class/b_class/c_class/finance/ops 六个 schema，
    没有 mart -> 裸查会抛 ProgrammingError。

    ⚠️⚠️ **不能用「try/except 包住裸查」来容错**：PostgreSQL 里一条语句失败会让
    **整个事务进入 aborted 状态**，后续所有语句都抛 `InFailedSQLTransactionError`。
    那样「查不到就回落日常档」的承诺根本不成立——不是这里返回空 dict，
    而是整个调用方在后面某处 500。

    正确做法（两步）：
    1. 先用 ``SELECT to_regclass('mart.inventory_age_current')`` 探测表是否存在——
       不存在就**根本不发出那条会失败的查询**，事务毫发无损；
    2. 万一表存在但查询仍失败（列变了、权限不足等），用 ``db.begin_nested()`` 开一个
       SAVEPOINT 包住它，异常时只回滚到保存点，外层事务仍然可用。
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
                await db.execute(text("SELECT to_regclass('mart.inventory_age_current')"))
            ).scalar()
            if not exists:
                # mart 层不存在：不发出会失败的查询，事务保持健康
                return {}
            age_rows = (
                await db.execute(
                    _AGE_LOOKUP_STMT,
                    {"keys": list(key_to_sku)},
                )
            ).all()
    except Exception as exc:  # noqa: BLE001
        # 保存点回滚后外层事务仍可用：按无库龄处理，回落「日常」档。
        # ⚠️ 必须留日志：表不存在、列改名、权限不足、SQL 拼错、类型推断失败
        # 全部退化成同一种「无库龄数据」，不记日志的话，库龄管道坏了运维无从发现。
        from modules.core.logger import get_logger

        get_logger(__name__).warning(
            "inventory age lookup failed, falling back to the base tier: %s", exc
        )
        return {}

    result: dict[int, dict] = {}
    for row in age_rows:
        sku_id = key_to_sku.get(row.product_sku)
        if sku_id is None:
            continue
        result[sku_id] = {
            "age_days": int(row.age_days) if row.age_days is not None else None,
            "current_qty": int(row.current_qty or 0),
            "inventory_value": float(row.inventory_value or 0.0),
        }
    return result
