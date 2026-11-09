"""仓名别名维护接口 —— ``core.dim_warehouse_name_aliases`` 的增删改查。

为什么需要这个接口
------------------
这张表以前**只能靠发迁移来改**（迁移里内联播种 5 条），运维上不可接受：
新开一个仓、或妙手改了仓名，都得等一次发版。

口径纪律
--------
* **登记载体** = ``core.dim_warehouse_name_aliases``（本接口维护它）
* **归一实现** = ``semantic.resolve_warehouse_code``（SQL 函数，全站唯一）
  —— 本接口**不**实现任何归一逻辑,只登记。
* 登记值**必须**指向 ``core.dim_warehouses`` 里真实存在的仓码：
  指向不存在的仓码会让库存行挂在一个不存在的仓上（外键兜底,这里再挡一层友好提示）。

改了之后必须做的两件事
----------------------
1. **回填 ``mart.inventory_state.warehouse_code``** —— 状态层是**表**不是视图,
   别名改了不会自动生效 ⇒ 这里显式按新映射重算一遍。
2. 语义层 / 快照族 / 滞销族都是**视图**,仓码是查询时实时算的 ⇒ **无需刷新**。
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import require_admin
from backend.models.database import get_async_db
from backend.schemas.warehouse_name_alias import (
    WarehouseNameAliasCreate,
    WarehouseNameAliasListResponse,
    WarehouseNameAliasResponse,
    WarehouseNameAliasUpdate,
)
from modules.core.db import DimWarehouse, DimWarehouseNameAlias
from modules.core.logger import get_logger


router = APIRouter(
    prefix="/warehouse-name-aliases",
    tags=["Warehouse Name Aliases"],
    dependencies=[Depends(require_admin)],
)

logger = get_logger(__name__)


def _serialize_alias(record: DimWarehouseNameAlias) -> WarehouseNameAliasResponse:
    return WarehouseNameAliasResponse(
        source_warehouse_name=record.source_warehouse_name,
        warehouse_code=record.warehouse_code,
        source=record.source,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


async def _assert_warehouse_exists(db: AsyncSession, warehouse_code: str) -> DimWarehouse:
    """仓码必须已登记在 ``core.dim_warehouses``（友好预检，FK 是最后一道兜底）。"""
    warehouse = (
        await db.execute(
            select(DimWarehouse).where(DimWarehouse.warehouse_code == warehouse_code)
        )
    ).scalar_one_or_none()
    if warehouse is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"warehouse code '{warehouse_code}' not found in core.dim_warehouses; "
                "register the warehouse first"
            ),
        )
    return warehouse


async def _rebuild_state_warehouse_codes(db: AsyncSession) -> None:
    """按当前映射重算状态层每一行的 ``warehouse_code``。

    为什么必须显式重算
    ------------------
    ``mart.inventory_state`` 是**表**不是视图 ⇒ 别名改了不会自动生效。
    这里用「查不到就是 NULL」的口径整体重算一遍 —— 与
    ``semantic.resolve_warehouse_code`` 完全一致（查不到 ⇒ 留空,绝不猜一个仓）。

    状态层只有几千行（生产实测 1,232 行）⇒ 全量重算是毫秒级。
    """
    await db.execute(
        text(
            """
            UPDATE mart.inventory_state s
               SET warehouse_code = (
                   SELECT a.warehouse_code
                     FROM core.dim_warehouse_name_aliases a
                    WHERE a.source_warehouse_name = s.warehouse_name
               )
            """
        )
    )


async def _load_unmapped_warehouse_names(db: AsyncSession) -> List[str]:
    """库存数据里出现、但**没有**登记映射的仓名（给运营的待办清单）。

    取不到（语义层视图尚未建立 / 库还没初始化）时返回空列表 ——
    提示信息缺失不该让整个列表接口失败。
    """
    try:
        result = await db.execute(
            text(
                """
                SELECT DISTINCT s.warehouse_name
                  FROM semantic.fact_inventory_snapshot s
                 WHERE NULLIF(TRIM(COALESCE(s.warehouse_name, '')), '') IS NOT NULL
                   AND NOT EXISTS (
                        SELECT 1
                          FROM core.dim_warehouse_name_aliases a
                         WHERE a.source_warehouse_name = s.warehouse_name
                   )
                 ORDER BY 1
                """
            )
        )
        return [row[0] for row in result.fetchall()]
    except Exception as exc:  # noqa: BLE001
        logger.warning("failed to list unmapped warehouse names: %s", exc)
        return []


@router.get("", response_model=WarehouseNameAliasListResponse)
async def list_warehouse_name_aliases(db: AsyncSession = Depends(get_async_db)):
    """列出全部仓名登记 + 库存里未登记的仓名。"""
    result = await db.execute(
        select(DimWarehouseNameAlias).order_by(DimWarehouseNameAlias.source_warehouse_name)
    )
    records = result.scalars().all()

    warehouses = {
        row[0]: row
        for row in (
            await db.execute(
                select(
                    DimWarehouse.warehouse_code,
                    DimWarehouse.warehouse_name,
                    DimWarehouse.country_code,
                )
            )
        ).all()
    }

    items = []
    for record in records:
        payload = _serialize_alias(record)
        warehouse = warehouses.get(record.warehouse_code)
        if warehouse is not None:
            payload.warehouse_name = warehouse[1]
            payload.country_code = warehouse[2]
        items.append(payload)

    return WarehouseNameAliasListResponse(
        items=items,
        count=len(items),
        unmapped_warehouse_names=await _load_unmapped_warehouse_names(db),
    )


@router.post("", response_model=WarehouseNameAliasResponse)
async def create_warehouse_name_alias(
    payload: WarehouseNameAliasCreate,
    db: AsyncSession = Depends(get_async_db),
):
    """登记一条「原始仓名 → 规范仓码」。"""
    source_name = payload.source_warehouse_name.strip()
    if not source_name:
        raise HTTPException(status_code=400, detail="source_warehouse_name is required")

    await _assert_warehouse_exists(db, payload.warehouse_code.strip())

    existing = (
        await db.execute(
            select(DimWarehouseNameAlias).where(
                DimWarehouseNameAlias.source_warehouse_name == source_name
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"warehouse name alias '{source_name}' already exists "
                f"(points to '{existing.warehouse_code}')"
            ),
        )

    record = DimWarehouseNameAlias(
        source_warehouse_name=source_name,
        warehouse_code=payload.warehouse_code.strip(),
        source=payload.source or "manual",
    )
    db.add(record)
    await db.flush()
    await _rebuild_state_warehouse_codes(db)
    await db.commit()
    await db.refresh(record)
    return _serialize_alias(record)


@router.put("/{source_warehouse_name}", response_model=WarehouseNameAliasResponse)
async def update_warehouse_name_alias(
    source_warehouse_name: str,
    payload: WarehouseNameAliasUpdate,
    db: AsyncSession = Depends(get_async_db),
):
    """改一条登记的指向（源仓名是主键,不可改）。"""
    record = (
        await db.execute(
            select(DimWarehouseNameAlias).where(
                DimWarehouseNameAlias.source_warehouse_name == source_warehouse_name
            )
        )
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"warehouse name alias '{source_warehouse_name}' not found",
        )

    await _assert_warehouse_exists(db, payload.warehouse_code.strip())
    record.warehouse_code = payload.warehouse_code.strip()
    if payload.source is not None:
        record.source = payload.source

    await db.flush()
    await _rebuild_state_warehouse_codes(db)
    await db.commit()
    await db.refresh(record)
    return _serialize_alias(record)


@router.delete("/{source_warehouse_name}")
async def delete_warehouse_name_alias(
    source_warehouse_name: str,
    db: AsyncSession = Depends(get_async_db),
):
    """删除一条登记。

    删除后,状态层里原本归到该仓的行**仓码回落为 NULL**（不静默归到别的仓）——
    与「查不到就留空」的口径一致。
    """
    record = (
        await db.execute(
            select(DimWarehouseNameAlias).where(
                DimWarehouseNameAlias.source_warehouse_name == source_warehouse_name
            )
        )
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"warehouse name alias '{source_warehouse_name}' not found",
        )

    await db.delete(record)
    await db.flush()
    await _rebuild_state_warehouse_codes(db)
    await db.commit()
    return {"message": f"warehouse name alias '{source_warehouse_name}' deleted"}
