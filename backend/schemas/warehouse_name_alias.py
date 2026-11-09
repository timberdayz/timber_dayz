"""仓名别名（``core.dim_warehouse_name_aliases``）的接口契约。

这张表登记的是「妙手导出的原始仓名 → 规范仓代码」。

为什么需要它
------------
妙手库存清单里的仓名是原始字符串（``新加坡`` / ``马来仓`` / ``菲律宾1店-儿童书包`` …），
而经营域用的是 ``core.dim_warehouses`` 里的规范仓代码
（``SG-01`` / ``MY-01`` / ``PH-01-CHILD`` …）。两边的**字符串本身就不一样**，
所以归一**不能靠字符串拼接去猜** —— 猜错的后果是**把货算到别的仓**
（仓错 ⇒ 库龄错 ⇒ 档位错 ⇒ 底线错 ⇒ 定价错，而且这种错在页面上完全看不出来）。

这张表是**唯一**的登记载体；归一规则由 ``semantic.resolve_warehouse_code``
（全站唯一实现）统一执行。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class WarehouseNameAliasCreate(BaseModel):
    """新增一条仓名 → 仓码 的登记。"""

    source_warehouse_name: str = Field(
        ...,
        description="妙手导出的原始仓名（如「新加坡」「菲律宾1店-儿童书包」）",
    )
    warehouse_code: str = Field(
        ...,
        description="规范仓代码（必须已存在于 core.dim_warehouses）",
    )
    source: Optional[str] = Field(
        default="manual",
        description="登记来源（manual / 导入文件名 / 其它）",
    )


class WarehouseNameAliasUpdate(BaseModel):
    """改一条登记的指向（源仓名不可改 —— 它是主键）。"""

    warehouse_code: str = Field(
        ...,
        description="新的规范仓代码（必须已存在于 core.dim_warehouses）",
    )
    source: Optional[str] = Field(default=None, description="登记来源")


class WarehouseNameAliasResponse(BaseModel):
    """一条仓名登记。"""

    source_warehouse_name: str
    warehouse_code: str
    warehouse_name: Optional[str] = Field(
        default=None, description="规范仓名（来自 core.dim_warehouses）"
    )
    country_code: Optional[str] = Field(
        default=None, description="仓所属国家（来自 core.dim_warehouses）"
    )
    source: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class WarehouseNameAliasListResponse(BaseModel):
    """仓名登记列表 + 库存数据里**还没登记**的仓名。

    ``unmapped_warehouse_names`` 是给运营的待办清单：库存里出现了这些仓名，
    但它们没有对应的规范仓码 ⇒ 这些行的仓级口径拿不到仓（不参与仓级定价）。
    """

    items: List[WarehouseNameAliasResponse]
    count: int
    unmapped_warehouse_names: List[str] = Field(default_factory=list)
