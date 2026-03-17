"""
2.15 分页工具单元测试

覆盖 backend/utils/pagination.py 中的 async_paginate_query()。
使用独立 SQLite 内存引擎（不依赖全局 Base，避免 JSONB 兼容问题）。
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.utils.pagination import async_paginate_query


# ---------------------------------------------------------------------------
# 测试专用 ORM 模型
# ---------------------------------------------------------------------------


class _PagBase(DeclarativeBase):
    pass


class _Product(_PagBase):
    __tablename__ = "test_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def pag_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(_PagBase.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        # 预插入 10 条记录
        for i in range(1, 11):
            session.add(_Product(name=f"product_{i:02d}"))
        await session.commit()
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(_PagBase.metadata.drop_all)
    await engine.dispose()


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------


class TestAsyncPaginateQuery:
    @pytest.mark.asyncio
    async def test_returns_tuple_of_list_and_int(self, pag_session: AsyncSession):
        stmt = select(_Product)
        data, total = await async_paginate_query(pag_session, stmt, page=1, page_size=5)
        assert isinstance(data, list)
        assert isinstance(total, int)

    @pytest.mark.asyncio
    async def test_total_equals_all_records(self, pag_session: AsyncSession):
        stmt = select(_Product)
        _, total = await async_paginate_query(pag_session, stmt, page=1, page_size=5)
        assert total == 10

    @pytest.mark.asyncio
    async def test_page_size_limits_results(self, pag_session: AsyncSession):
        stmt = select(_Product)
        data, _ = await async_paginate_query(pag_session, stmt, page=1, page_size=3)
        assert len(data) == 3

    @pytest.mark.asyncio
    async def test_second_page_returns_correct_slice(self, pag_session: AsyncSession):
        stmt = select(_Product).order_by(_Product.id)
        page1, _ = await async_paginate_query(pag_session, stmt, page=1, page_size=4)
        page2, _ = await async_paginate_query(pag_session, stmt, page=2, page_size=4)

        ids_page1 = {obj.id for obj in page1}
        ids_page2 = {obj.id for obj in page2}
        assert ids_page1.isdisjoint(ids_page2), "两页数据不应有重叠"

    @pytest.mark.asyncio
    async def test_last_page_may_have_fewer_items(self, pag_session: AsyncSession):
        stmt = select(_Product)
        data, total = await async_paginate_query(pag_session, stmt, page=2, page_size=7)
        # 第 2 页：10 - 7 = 3 条
        assert len(data) == 3
        assert total == 10

    @pytest.mark.asyncio
    async def test_page_beyond_total_returns_empty(self, pag_session: AsyncSession):
        stmt = select(_Product)
        data, total = await async_paginate_query(pag_session, stmt, page=99, page_size=5)
        assert data == []
        assert total == 10

    @pytest.mark.asyncio
    async def test_invalid_page_clamped_to_1(self, pag_session: AsyncSession):
        stmt = select(_Product)
        data, total = await async_paginate_query(pag_session, stmt, page=0, page_size=5)
        assert len(data) == 5
        assert total == 10

    @pytest.mark.asyncio
    async def test_invalid_page_size_clamped_to_10(self, pag_session: AsyncSession):
        stmt = select(_Product)
        data, total = await async_paginate_query(pag_session, stmt, page=1, page_size=0)
        assert len(data) == 10
        assert total == 10

    @pytest.mark.asyncio
    async def test_empty_table_returns_zero_total(self, pag_session: AsyncSession):
        # 使用带 WHERE 过滤不存在数据的查询模拟空结果
        stmt = select(_Product).where(_Product.name == "nonexistent")
        data, total = await async_paginate_query(pag_session, stmt, page=1, page_size=10)
        assert data == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_page_size_larger_than_total(self, pag_session: AsyncSession):
        stmt = select(_Product)
        data, total = await async_paginate_query(pag_session, stmt, page=1, page_size=100)
        assert len(data) == 10
        assert total == 10
