from __future__ import annotations

from typing import Any, Iterable, List, Tuple

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def async_paginate_query(
    db: AsyncSession,
    stmt: Select[Any],
    *,
    page: int,
    page_size: int,
) -> Tuple[List[Any], int]:
    """
    异步分页查询工具。

    返回值与 `backend.utils.api_response.pagination_response()` 兼容:
      - data_list: 当前页记录列表
      - total: 符合条件的总记录数
    """
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 10

    # 统计总数
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = int(total_result.scalar_one() or 0)

    # 查询当前页数据
    offset = (page - 1) * page_size
    page_stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(page_stmt)

    data: Iterable[Any] = result.scalars().all()
    return list(data), total


__all__ = ["async_paginate_query"]

