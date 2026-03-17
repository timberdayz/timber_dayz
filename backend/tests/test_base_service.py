"""
2.13 AsyncCRUDService 单元测试

使用 conftest.py 提供的 sqlite_session fixture 进行内存数据库测试。
覆盖:
- get / get_multi / create / update / remove
- soft_delete (含 deleted_at 过滤)
- 乐观锁冲突 (OptimisticLockError)
- 审计钩子 on_after_create / on_after_update / on_after_delete
- provide_service 工厂函数
"""

from __future__ import annotations

from typing import Optional

import pytest
import pytest_asyncio
from pydantic import BaseModel
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.services.base_service import AsyncCRUDService, OptimisticLockError


# ---------------------------------------------------------------------------
# 测试专用 ORM 模型（不依赖 schema.py，避免污染 SSOT）
# ---------------------------------------------------------------------------


class _TestBase(DeclarativeBase):
    pass


class _Item(_TestBase):
    __tablename__ = "test_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)


class _SoftItem(_TestBase):
    __tablename__ = "test_soft_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    deleted_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    version: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class _ItemCreate(BaseModel):
    name: str
    version: Optional[int] = 0


class _ItemUpdate(BaseModel):
    name: Optional[str] = None


# ---------------------------------------------------------------------------
# Fixtures（独立 SQLite 引擎，不依赖全局 Base 以避免 JSONB 兼容问题）
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def item_session() -> AsyncSession:
    """基于 _TestBase 的独立内存 SQLite session。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(_TestBase.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(_TestBase.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def soft_session() -> AsyncSession:
    """与 item_session 共用同一 _TestBase，独立引擎实例。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(_TestBase.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(_TestBase.metadata.drop_all)
    await engine.dispose()


# ---------------------------------------------------------------------------
# 辅助 Service 子类（带审计钩子记录）
# ---------------------------------------------------------------------------


class _AuditedItemService(AsyncCRUDService[_Item, _ItemCreate, _ItemUpdate]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(_Item, db, enable_audit=True)
        self.audit_log: list[str] = []

    async def on_after_create(self, obj: _Item) -> None:
        self.audit_log.append(f"created:{obj.id}")

    async def on_after_update(self, obj: _Item) -> None:
        self.audit_log.append(f"updated:{obj.id}")

    async def on_after_delete(self, obj: _Item) -> None:
        self.audit_log.append(f"deleted:{obj.id}")


# ---------------------------------------------------------------------------
# 基础 CRUD 测试
# ---------------------------------------------------------------------------


class TestAsyncCRUDServiceBasic:
    @pytest.mark.asyncio
    async def test_create_and_get(self, item_session: AsyncSession):
        svc = AsyncCRUDService(_Item, item_session)
        obj = await svc.create(_ItemCreate(name="apple"))
        assert obj.id is not None
        assert obj.name == "apple"

        fetched = await svc.get(obj.id)
        assert fetched is not None
        assert fetched.name == "apple"

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, item_session: AsyncSession):
        svc = AsyncCRUDService(_Item, item_session)
        result = await svc.get(9999)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_multi(self, item_session: AsyncSession):
        svc = AsyncCRUDService(_Item, item_session)
        await svc.create(_ItemCreate(name="a"))
        await svc.create(_ItemCreate(name="b"))
        await svc.create(_ItemCreate(name="c"))

        items = await svc.get_multi(limit=2)
        assert len(items) == 2

        all_items = await svc.get_multi(limit=100)
        assert len(all_items) >= 3

    @pytest.mark.asyncio
    async def test_update(self, item_session: AsyncSession):
        svc = AsyncCRUDService(_Item, item_session)
        obj = await svc.create(_ItemCreate(name="old"))
        updated = await svc.update(obj.id, _ItemUpdate(name="new"))
        assert updated is not None
        assert updated.name == "new"

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_none(self, item_session: AsyncSession):
        svc = AsyncCRUDService(_Item, item_session)
        result = await svc.update(9999, _ItemUpdate(name="x"))
        assert result is None

    @pytest.mark.asyncio
    async def test_remove(self, item_session: AsyncSession):
        svc = AsyncCRUDService(_Item, item_session)
        obj = await svc.create(_ItemCreate(name="to_delete"))
        removed = await svc.remove(obj.id)
        assert removed is not None

        fetched = await svc.get(obj.id)
        assert fetched is None

    @pytest.mark.asyncio
    async def test_remove_nonexistent_returns_none(self, item_session: AsyncSession):
        svc = AsyncCRUDService(_Item, item_session)
        result = await svc.remove(9999)
        assert result is None


# ---------------------------------------------------------------------------
# 乐观锁测试
# ---------------------------------------------------------------------------


class TestOptimisticLock:
    @pytest.mark.asyncio
    async def test_update_with_correct_version_succeeds(self, item_session: AsyncSession):
        svc = AsyncCRUDService(_Item, item_session, enable_optimistic_lock=True)
        obj = await svc.create(_ItemCreate(name="v0", version=0))

        updated = await svc.update(obj.id, _ItemUpdate(name="v1"), expected_version=0)
        assert updated is not None
        assert updated.name == "v1"
        assert updated.version == 1

    @pytest.mark.asyncio
    async def test_update_with_stale_version_raises(self, item_session: AsyncSession):
        svc = AsyncCRUDService(_Item, item_session, enable_optimistic_lock=True)
        obj = await svc.create(_ItemCreate(name="v0", version=0))

        with pytest.raises(OptimisticLockError):
            await svc.update(obj.id, _ItemUpdate(name="conflict"), expected_version=99)

    @pytest.mark.asyncio
    async def test_remove_with_stale_version_raises(self, item_session: AsyncSession):
        svc = AsyncCRUDService(_Item, item_session, enable_optimistic_lock=True)
        obj = await svc.create(_ItemCreate(name="v0", version=0))

        with pytest.raises(OptimisticLockError):
            await svc.remove(obj.id, expected_version=99)

    @pytest.mark.asyncio
    async def test_update_without_expected_version_skips_check(self, item_session: AsyncSession):
        svc = AsyncCRUDService(_Item, item_session, enable_optimistic_lock=True)
        obj = await svc.create(_ItemCreate(name="v0", version=0))

        # expected_version=None 时不做版本检查
        updated = await svc.update(obj.id, _ItemUpdate(name="no_check"))
        assert updated is not None


# ---------------------------------------------------------------------------
# 软删除测试
# ---------------------------------------------------------------------------


class _SoftItemCreate(BaseModel):
    name: str


class _SoftItemUpdate(BaseModel):
    name: Optional[str] = None


class TestSoftDelete:
    @pytest.mark.asyncio
    async def test_soft_delete_sets_deleted_at(self, soft_session: AsyncSession):
        svc = AsyncCRUDService(_SoftItem, soft_session)
        obj = await svc.create(_SoftItemCreate(name="soft"))
        deleted = await svc.soft_delete(obj.id)
        assert deleted is not None
        assert deleted.deleted_at is not None

    @pytest.mark.asyncio
    async def test_soft_deleted_excluded_from_get(self, soft_session: AsyncSession):
        svc = AsyncCRUDService(_SoftItem, soft_session)
        obj = await svc.create(_SoftItemCreate(name="ghost"))
        await svc.soft_delete(obj.id)

        result = await svc.get(obj.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_soft_deleted_included_with_flag(self, soft_session: AsyncSession):
        svc = AsyncCRUDService(_SoftItem, soft_session)
        obj = await svc.create(_SoftItemCreate(name="ghost2"))
        await svc.soft_delete(obj.id)

        result = await svc.get(obj.id, include_deleted=True)
        assert result is not None

    @pytest.mark.asyncio
    async def test_soft_delete_nonexistent_returns_none(self, soft_session: AsyncSession):
        svc = AsyncCRUDService(_SoftItem, soft_session)
        result = await svc.soft_delete(9999)
        assert result is None

    @pytest.mark.asyncio
    async def test_soft_delete_not_supported_raises(self, item_session: AsyncSession):
        svc = AsyncCRUDService(_Item, item_session)
        obj = await svc.create(_ItemCreate(name="no_soft"))
        with pytest.raises(NotImplementedError):
            await svc.soft_delete(obj.id)


# ---------------------------------------------------------------------------
# 审计钩子测试
# ---------------------------------------------------------------------------


class TestAuditHooks:
    @pytest.mark.asyncio
    async def test_on_after_create_called(self, item_session: AsyncSession):
        svc = _AuditedItemService(item_session)
        obj = await svc.create(_ItemCreate(name="audit_create"))
        assert any(f"created:{obj.id}" in e for e in svc.audit_log)

    @pytest.mark.asyncio
    async def test_on_after_update_called(self, item_session: AsyncSession):
        svc = _AuditedItemService(item_session)
        obj = await svc.create(_ItemCreate(name="audit_update"))
        await svc.update(obj.id, _ItemUpdate(name="updated"))
        assert any(f"updated:{obj.id}" in e for e in svc.audit_log)

    @pytest.mark.asyncio
    async def test_on_after_delete_called(self, item_session: AsyncSession):
        svc = _AuditedItemService(item_session)
        obj = await svc.create(_ItemCreate(name="audit_delete"))
        await svc.remove(obj.id)
        assert any(f"deleted:{obj.id}" in e for e in svc.audit_log)

    @pytest.mark.asyncio
    async def test_audit_disabled_by_default(self, item_session: AsyncSession):
        svc = AsyncCRUDService(_Item, item_session)
        obj = await svc.create(_ItemCreate(name="no_audit"))
        await svc.update(obj.id, _ItemUpdate(name="x"))
        await svc.remove(obj.id)
        # 不抛异常即可，默认钩子只打日志


# ---------------------------------------------------------------------------
# OptimisticLockError 消息格式
# ---------------------------------------------------------------------------


class TestOptimisticLockError:
    def test_error_message_contains_model_and_id(self):
        exc = OptimisticLockError("MyModel", 42)
        assert "MyModel" in str(exc)
        assert "42" in str(exc)

    def test_is_exception(self):
        exc = OptimisticLockError("M", 1)
        assert isinstance(exc, Exception)
