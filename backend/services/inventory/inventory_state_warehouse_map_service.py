"""妙手原始仓名 → 规范仓代码 的归一。

背景
----
库存采集写进 ``mart.inventory_state.warehouse_name`` 的是**妙手导出的原始字符串**
（生产实测：``新加坡``、``马来仓``、``菲律宾1店-儿童书包``、``菲律宾仓库（维修工具）``、
``菲律宾3店-时尚箱包``），而经营域用的是 ``core.dim_warehouses`` 里的规范仓代码
（``SG-01`` / ``MY-01`` / ``PH-01-CHILD`` / ``PH-REPAIR`` / ``PH-03-FASHION``）。

两边的**字符串本身就不一样**（规范仓名带「仓」字后缀，原始仓名不带），
所以归一**不能靠字符串拼接去猜**：猜错的后果是**把货算到别的仓** ——
仓错 ⇒ 库龄错 ⇒ 档位错 ⇒ 底线错 ⇒ 定价错，而且这种错**在页面上完全看不出来**。

所以归一走**显式登记**的对照表 ``core.dim_warehouse_name_aliases``：
查得到就归一，查不到就**留空并记日志**，绝不静默归到一个仓。

为什么不能靠「去掉仓字后缀」这类规则
----------------------------------
「新加坡」去掉后缀是「新加坡」，而规范仓名是「新加坡仓」 —— 规则得写成
「原始名 + 仓 == 规范名」，但「马来仓」原始名本来就带「仓」，套同一条规则会变成
「马来仓仓」；而「菲律宾仓库（维修工具）」去掉「仓库」又对不上「菲律宾仓（维修工具）」。
规则一多就必然出现某个仓漏配或错配 —— 而漏配的代价是**静默算错价**。
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import DimWarehouseNameAlias
from modules.core.logger import get_logger


class WarehouseNameResolver:
    """仓名归一器：一次载入映射，整轮刷新复用。

    为什么做成对象而不是每次查库
    ----------------------------
    采集一轮会写上千行，每行都查一次映射表是**同一条查询跑上千遍**。
    映射表是主数据级的、极小（生产 5 行）、且**只在人工维护时才变**，
    所以一轮刷新读一次就够 —— 写进去的每一行用的是同一份快照，
    不会出现「同一轮里前半段用旧映射、后半段用新映射」的撕裂。
    """

    def __init__(self, alias_map: dict[str, str]) -> None:
        self._alias_map = alias_map

    @classmethod
    async def load(cls, db: AsyncSession) -> "WarehouseNameResolver":
        """从对照表载入映射。

        表不存在（迁移未跑）时返回**空映射**：此时所有仓名都归一不出来，
        ``warehouse_code`` 留空 —— 这比"猜一个仓"安全得多。
        """
        try:
            rows = (
                await db.execute(
                    select(
                        DimWarehouseNameAlias.source_warehouse_name,
                        DimWarehouseNameAlias.warehouse_code,
                    )
                )
            ).all()
        except Exception as exc:  # noqa: BLE001
            get_logger(__name__).warning(
                "warehouse alias table unavailable, warehouse codes stay empty: %s",
                exc,
            )
            return cls({})
        return cls({row[0]: row[1] for row in rows})

    def resolve(self, warehouse_name: Optional[str]) -> Optional[str]:
        """把原始仓名解析成规范仓代码。

        解析不出来就返回 ``None`` —— 调用方据此把 ``warehouse_code`` 留空。
        """
        if not warehouse_name:
            return None
        return self._alias_map.get(warehouse_name)

    def annotate_unresolved(self, warehouse_names: list[str]) -> None:
        """把没配到映射的仓名记一条日志。

        ⚠️ **只记一次每个仓名**：一轮刷新可能刷到几万个同名仓行，
        逐行记日志会把日志淹掉，把真正要看的信号冲掉。
        """
        missing = sorted(
            {name for name in warehouse_names if name and name not in self._alias_map}
        )
        if not missing:
            return
        get_logger(__name__).warning(
            "warehouse names without alias mapping (warehouse_code left empty): %s",
            ", ".join(missing),
        )


async def load_warehouse_name_resolver(db: AsyncSession) -> WarehouseNameResolver:
    """便捷入口：载入库名归一器。"""
    return await WarehouseNameResolver.load(db)
