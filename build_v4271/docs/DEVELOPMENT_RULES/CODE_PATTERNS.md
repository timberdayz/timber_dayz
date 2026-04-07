# 代码模式模板 - Agent 开发参考

**版本**: v4.20.0  
**更新**: 2026-03-16  
**标准**: 企业级代码模式模板（可直接复制使用）

---

## 目录

1. [AsyncCRUDService 子类模板](#1-asynccrudservice-子类模板)
2. [@transactional 装饰器模板](#2-transactional-装饰器模板)
3. [Router 文件模板](#3-router-文件模板)
4. [Schema 文件模板](#4-schema-文件模板)
5. [conftest.py 测试 Fixture 模板](#5-conftestpy-测试-fixture-模板)
6. [Cache-Aside 缓存模式](#6-cache-aside-缓存模式)
7. [乐观锁模式](#7-乐观锁模式)
8. [依赖注入工厂函数模式](#8-依赖注入工厂函数模式)

---

## 1. AsyncCRUDService 子类模板

通用异步 CRUD 基类，适配 SQLAlchemy ORM + Pydantic schema。

### 1.1 基类定义

```python
# backend/services/base_crud.py
from typing import Any, Generic, List, Optional, Type, TypeVar

from datetime import datetime, timezone
from pydantic import BaseModel
from sqlalchemy import select, func, inspect
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.logger import get_logger

logger = get_logger(__name__)

ModelType = TypeVar("ModelType")
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class OptimisticLockError(Exception):
    """乐观锁冲突异常"""

    def __init__(self, model_name: str, record_id: Any):
        self.model_name = model_name
        self.record_id = record_id
        super().__init__(
            f"[CONFLICT] {model_name}(id={record_id}) has been modified by another transaction"
        )


class AsyncCRUDService(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """
    通用异步 CRUD 服务基类

    特性:
    - 自动软删除过滤: 模型含 deleted_at 字段时, get/get_multi 自动排除已删除记录
    - 可选审计钩子: 设置 enable_audit=True 后触发 on_after_create/update/delete
    - 可选乐观锁: 设置 enable_optimistic_lock=True 后 update/remove 检查 version 字段

    Args:
        model: SQLAlchemy ORM 模型类
        db: 异步数据库 Session
    """

    def __init__(
        self,
        model: Type[ModelType],
        db: AsyncSession,
        *,
        enable_audit: bool = False,
        enable_optimistic_lock: bool = False,
    ) -> None:
        self.model = model
        self.db = db
        self.enable_audit = enable_audit
        self.enable_optimistic_lock = enable_optimistic_lock
        self._has_deleted_at = self._check_column_exists("deleted_at")
        self._has_version = self._check_column_exists("version")

    def _check_column_exists(self, column_name: str) -> bool:
        """检查模型是否拥有指定字段"""
        mapper = inspect(self.model)
        return column_name in [c.key for c in mapper.column_attrs]

    def _apply_soft_delete_filter(self, stmt: Any, include_deleted: bool = False) -> Any:
        """若模型含 deleted_at, 自动追加 WHERE deleted_at IS NULL"""
        if self._has_deleted_at and not include_deleted:
            stmt = stmt.where(getattr(self.model, "deleted_at").is_(None))
        return stmt

    # ------ Read ------

    async def get(
        self, id: Any, *, include_deleted: bool = False
    ) -> Optional[ModelType]:
        stmt = select(self.model).where(self.model.id == id)
        stmt = self._apply_soft_delete_filter(stmt, include_deleted)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_multi(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        include_deleted: bool = False,
    ) -> List[ModelType]:
        stmt = select(self.model).offset(skip).limit(limit)
        stmt = self._apply_soft_delete_filter(stmt, include_deleted)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # ------ Create ------

    async def create(self, obj_in: CreateSchemaType) -> ModelType:
        obj_data = obj_in.model_dump()
        db_obj = self.model(**obj_data)
        self.db.add(db_obj)
        await self.db.flush()
        await self.db.refresh(db_obj)

        if self.enable_audit:
            await self.on_after_create(db_obj)

        return db_obj

    # ------ Update ------

    async def update(
        self,
        id: Any,
        obj_in: UpdateSchemaType,
        *,
        expected_version: Optional[int] = None,
    ) -> Optional[ModelType]:
        db_obj = await self.get(id)
        if db_obj is None:
            return None

        if self.enable_optimistic_lock and self._has_version:
            if expected_version is not None and db_obj.version != expected_version:
                raise OptimisticLockError(self.model.__name__, id)

        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)

        if self._has_version:
            db_obj.version = (db_obj.version or 0) + 1

        await self.db.flush()
        await self.db.refresh(db_obj)

        if self.enable_audit:
            await self.on_after_update(db_obj)

        return db_obj

    # ------ Delete (hard) ------

    async def remove(
        self,
        id: Any,
        *,
        expected_version: Optional[int] = None,
    ) -> Optional[ModelType]:
        db_obj = await self.get(id)
        if db_obj is None:
            return None

        if self.enable_optimistic_lock and self._has_version:
            if expected_version is not None and db_obj.version != expected_version:
                raise OptimisticLockError(self.model.__name__, id)

        await self.db.delete(db_obj)
        await self.db.flush()

        if self.enable_audit:
            await self.on_after_delete(db_obj)

        return db_obj

    # ------ Soft Delete ------

    async def soft_delete(self, id: Any) -> Optional[ModelType]:
        """软删除: 设置 deleted_at 时间戳, 不物理移除记录"""
        if not self._has_deleted_at:
            raise NotImplementedError(
                f"{self.model.__name__} does not have deleted_at column"
            )

        db_obj = await self.get(id)
        if db_obj is None:
            return None

        db_obj.deleted_at = datetime.now(timezone.utc)

        if self._has_version:
            db_obj.version = (db_obj.version or 0) + 1

        await self.db.flush()
        await self.db.refresh(db_obj)

        if self.enable_audit:
            await self.on_after_delete(db_obj)

        return db_obj

    # ------ Audit Hooks (子类可覆盖) ------

    async def on_after_create(self, obj: ModelType) -> None:
        """创建后审计钩子 (子类按需覆盖)"""
        logger.info("[AUDIT] Created %s(id=%s)", self.model.__name__, obj.id)

    async def on_after_update(self, obj: ModelType) -> None:
        """更新后审计钩子 (子类按需覆盖)"""
        logger.info("[AUDIT] Updated %s(id=%s)", self.model.__name__, obj.id)

    async def on_after_delete(self, obj: ModelType) -> None:
        """删除后审计钩子 (子类按需覆盖)"""
        logger.info("[AUDIT] Deleted %s(id=%s)", self.model.__name__, obj.id)
```

### 1.2 具体子类示例

```python
# backend/services/order_service.py
from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas.order import OrderCreate, OrderUpdate
from backend.services.base_crud import AsyncCRUDService
from modules.core.db import FactOrder


class OrderService(AsyncCRUDService[FactOrder, OrderCreate, OrderUpdate]):
    """订单 CRUD 服务"""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(
            model=FactOrder,
            db=db,
            enable_audit=True,
            enable_optimistic_lock=True,
        )

    async def on_after_create(self, obj: FactOrder) -> None:
        logger.info("[AUDIT] Order created: order_id=%s", obj.id)
```

---

## 2. @transactional 装饰器模板

基于 Savepoint 的事务装饰器，与 `get_async_db()` 配合使用。

### 2.1 核心原理

- `get_async_db()` 负责最终 `commit`（请求结束时提交）
- `@transactional` 只创建 `begin_nested()`（Savepoint），出错则回滚到 savepoint
- 嵌套调用时自动创建更深层的 savepoint

### 2.2 装饰器实现

```python
# backend/utils/transactional.py
import functools
from typing import Callable, TypeVar, ParamSpec

from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.logger import get_logger

logger = get_logger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def transactional(func: Callable[P, R]) -> Callable[P, R]:
    """
    Savepoint-based transaction decorator.

    Requirements:
      - Decorated function MUST have a parameter named 'db' of type AsyncSession.
      - Final commit is performed by get_async_db() at request end.
      - Nested @transactional calls create deeper savepoints.

    Usage:
      @transactional
      async def transfer(db: AsyncSession, from_id: int, to_id: int, amount: Decimal):
          ...
    """

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        db: AsyncSession | None = kwargs.get("db")
        if db is None:
            for arg in args:
                if isinstance(arg, AsyncSession):
                    db = arg
                    break

        if db is None:
            raise RuntimeError(
                "@transactional requires a 'db: AsyncSession' parameter"
            )

        async with db.begin_nested():
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception:
                logger.error(
                    "[ROLLBACK] Savepoint rolled back in %s", func.__qualname__
                )
                raise

    return wrapper
```

### 2.3 使用示例

```python
from decimal import Decimal
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.utils.transactional import transactional
from modules.core.db import FactWallet


@transactional
async def transfer_balance(
    db: AsyncSession,
    from_id: int,
    to_id: int,
    amount: Decimal,
) -> None:
    """转账操作: 若任一步失败, savepoint 自动回滚, 不影响外层事务"""
    await db.execute(
        update(FactWallet)
        .where(FactWallet.id == from_id)
        .values(balance=FactWallet.balance - amount)
    )
    await db.execute(
        update(FactWallet)
        .where(FactWallet.id == to_id)
        .values(balance=FactWallet.balance + amount)
    )


# 嵌套事务: 内层 savepoint 独立回滚, 不影响外层
@transactional
async def process_order(db: AsyncSession, order_id: int) -> None:
    # step 1: create order ...
    # step 2: nested savepoint
    await transfer_balance(db=db, from_id=1, to_id=2, amount=Decimal("100.00"))
    # step 3: continue ...
```

---

## 3. Router 文件模板

标准 FastAPI 路由文件，遵循 Contract-First 规范。

```python
# backend/routers/my_feature.py
"""
我的功能模块 - API 路由

[OK] response_model 100% 覆盖
[OK] Pydantic 模型全部来自 backend.schemas
[OK] 使用 get_async_db() 异步 Session
[OK] <= 15 个端点
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_async_db
from backend.routers.auth import get_current_user
from backend.schemas.my_feature import (
    ItemCreate,
    ItemListResponse,
    ItemResponse,
    ItemUpdate,
)
from backend.services.my_feature_service import MyFeatureService
from modules.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/my-feature", tags=["My Feature"])


def get_service(db: AsyncSession = Depends(get_async_db)) -> MyFeatureService:
    """服务工厂 (Depends 注入)"""
    return MyFeatureService(db)


@router.get(
    "/items",
    response_model=ItemListResponse,
    summary="获取列表",
)
async def list_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    service: MyFeatureService = Depends(get_service),
    current_user=Depends(get_current_user),
) -> ItemListResponse:
    """获取分页列表"""
    items = await service.get_multi(skip=skip, limit=limit)
    return ItemListResponse(success=True, data=items)


@router.get(
    "/items/{item_id}",
    response_model=ItemResponse,
    summary="获取详情",
)
async def get_item(
    item_id: int,
    service: MyFeatureService = Depends(get_service),
    current_user=Depends(get_current_user),
) -> ItemResponse:
    """获取单条记录"""
    item = await service.get(item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item {item_id} not found",
        )
    return ItemResponse(success=True, data=item)


@router.post(
    "/items",
    response_model=ItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建",
)
async def create_item(
    payload: ItemCreate,
    service: MyFeatureService = Depends(get_service),
    current_user=Depends(get_current_user),
) -> ItemResponse:
    """创建新记录"""
    item = await service.create(payload)
    return ItemResponse(success=True, data=item, message="Created successfully")


@router.put(
    "/items/{item_id}",
    response_model=ItemResponse,
    summary="更新",
)
async def update_item(
    item_id: int,
    payload: ItemUpdate,
    service: MyFeatureService = Depends(get_service),
    current_user=Depends(get_current_user),
) -> ItemResponse:
    """更新记录"""
    item = await service.update(item_id, payload)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item {item_id} not found",
        )
    return ItemResponse(success=True, data=item, message="Updated successfully")


@router.delete(
    "/items/{item_id}",
    response_model=ItemResponse,
    summary="删除",
)
async def delete_item(
    item_id: int,
    service: MyFeatureService = Depends(get_service),
    current_user=Depends(get_current_user),
) -> ItemResponse:
    """删除记录(软删除)"""
    item = await service.soft_delete(item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item {item_id} not found",
        )
    return ItemResponse(success=True, data=item, message="Deleted successfully")
```

---

## 4. Schema 文件模板

Pydantic 请求/响应模型，遵循 Contract-First 第 2 步。

### 4.1 Schema 文件

```python
# backend/schemas/my_feature.py
"""
My Feature - Pydantic Schemas (Contract-First)

请求/响应模型定义。Router 文件只从此处导入, 禁止在 routers/ 中定义模型。
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ==================== 请求模型 ====================

class ItemCreate(BaseModel):
    """创建请求"""
    name: str = Field(..., min_length=1, max_length=200, description="名称")
    description: Optional[str] = Field(None, max_length=1000, description="描述")
    category: str = Field(..., description="分类")
    amount: float = Field(..., gt=0, description="金额")


class ItemUpdate(BaseModel):
    """更新请求 (所有字段可选)"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    category: Optional[str] = None
    amount: Optional[float] = Field(None, gt=0)


# ==================== 响应模型 ====================

class ItemData(BaseModel):
    """单条记录数据"""
    id: int
    name: str
    description: Optional[str] = None
    category: str
    amount: float
    version: int = 1
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ItemResponse(BaseModel):
    """单条记录响应"""
    success: bool = True
    data: ItemData
    message: Optional[str] = None


class ItemListResponse(BaseModel):
    """列表响应"""
    success: bool = True
    data: List[ItemData]
    message: Optional[str] = None
```

### 4.2 注册到 schemas/\_\_init\_\_.py

```python
# backend/schemas/__init__.py  (追加)

# ==================== My Feature ====================
from backend.schemas.my_feature import (
    ItemCreate,
    ItemUpdate,
    ItemData,
    ItemResponse,
    ItemListResponse,
)
```

---

## 5. conftest.py 测试 Fixture 模板

支持 SQLite 快速单元测试 + PostgreSQL 集成测试的双模式配置。

```python
# backend/tests/conftest.py
"""
测试 Fixture 配置

- sqlite_session: 内存 SQLite, 快速单元测试
- pg_session: testcontainers PostgreSQL, 集成测试
- async_client: 带 DB override 的 FastAPI TestClient
- auth_headers: Mock JWT 认证头
"""

import asyncio
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from modules.core.db import Base

# ---------- Markers ----------

def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "pg_only: mark test to run only with PostgreSQL"
    )


# ---------- Event loop ----------

@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ========== SQLite (fast unit tests) ==========

@pytest_asyncio.fixture
async def sqlite_session() -> AsyncGenerator[AsyncSession, None]:
    """In-memory SQLite async session for unit tests"""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


# ========== PostgreSQL (integration tests via testcontainers) ==========

@pytest_asyncio.fixture(scope="session")
async def pg_engine():
    """Session-scoped PostgreSQL engine via testcontainers"""
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers not installed")

    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        async_url = sync_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        engine = create_async_engine(async_url, echo=False)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        yield engine
        await engine.dispose()


@pytest_asyncio.fixture
async def pg_session(pg_engine) -> AsyncGenerator[AsyncSession, None]:
    """Per-test PostgreSQL session with rollback isolation"""
    session_factory = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with session_factory() as session:
        await session.begin()
        yield session
        await session.rollback()


# ========== FastAPI AsyncClient ==========

@pytest_asyncio.fixture
async def async_client(sqlite_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient with get_async_db override"""
    from backend.main import app
    from backend.models.database import get_async_db

    async def override_get_async_db():
        yield sqlite_session

    app.dependency_overrides[get_async_db] = override_get_async_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ========== Auth Helpers ==========

@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Mock JWT auth headers for testing (skip real token validation)"""
    from backend.routers.auth import get_current_user

    from backend.main import app

    mock_user = type("MockUser", (), {
        "id": 1,
        "username": "test_admin",
        "is_active": True,
        "role_id": 1,
    })()

    async def override_current_user():
        return mock_user

    app.dependency_overrides[get_current_user] = override_current_user

    return {"Authorization": "Bearer test-token-for-unit-tests"}
```

### 5.1 使用示例

```python
# backend/tests/test_my_feature.py
import pytest
import pytest_asyncio


@pytest.mark.asyncio
async def test_create_item_sqlite(async_client, auth_headers):
    """[Unit] SQLite fast test"""
    resp = await async_client.post(
        "/api/my-feature/items",
        json={"name": "Test", "category": "A", "amount": 99.9},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["name"] == "Test"


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_create_item_pg(pg_session):
    """[Integration] PostgreSQL test"""
    from backend.services.my_feature_service import MyFeatureService
    from backend.schemas.my_feature import ItemCreate

    service = MyFeatureService(pg_session)
    item = await service.create(ItemCreate(name="PG Test", category="B", amount=50.0))
    assert item.id is not None
```

---

## 6. Cache-Aside 缓存模式

使用项目已有的 `CacheService`（L2 Redis）配合进程内字典实现 L1 缓存。

### 6.1 双层缓存封装

```python
# backend/utils/cache_aside.py
"""
Cache-Aside pattern (L1 in-process + L2 Redis)

L1: 进程内字典, TTL 300s, 适用于配置/枚举等低变更数据
L2: Redis (CacheService), TTL 600s, 适用于会话/频繁查询
"""

import time
from typing import Any, Callable, Optional

from modules.core.logger import get_logger

logger = get_logger(__name__)


class L1Cache:
    """进程内 TTL 缓存 (简易实现)"""

    def __init__(self, default_ttl: int = 300) -> None:
        self._store: dict[str, tuple[Any, float]] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        expires_at = time.monotonic() + (ttl or self._default_ttl)
        self._store[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()


# Singleton
_l1 = L1Cache(default_ttl=300)


async def cache_aside_get(
    key: str,
    fetcher: Callable[[], Any],
    cache_service: Optional[Any] = None,
    l1_ttl: int = 300,
    l2_ttl: int = 600,
) -> Any:
    """
    Cache-Aside 读取:
      1. L1 hit -> return
      2. L2 hit -> fill L1, return
      3. miss  -> call fetcher, fill L1+L2, return
    """
    # L1
    result = _l1.get(key)
    if result is not None:
        logger.debug("[CACHE] L1 hit: %s", key)
        return result

    # L2 (Redis)
    if cache_service is not None:
        result = await cache_service.get(key)
        if result is not None:
            logger.debug("[CACHE] L2 hit: %s", key)
            _l1.set(key, result, l1_ttl)
            return result

    # Miss -> fetch from source
    logger.debug("[CACHE] Miss: %s, fetching from source", key)
    result = await fetcher()

    _l1.set(key, result, l1_ttl)
    if cache_service is not None:
        await cache_service.set(key, result, l2_ttl)

    return result


async def cache_aside_invalidate(
    key: str,
    cache_service: Optional[Any] = None,
) -> None:
    """写入后失效: 同时清除 L1 + L2"""
    _l1.delete(key)
    if cache_service is not None:
        await cache_service.delete(key)
    logger.debug("[CACHE] Invalidated: %s", key)
```

### 6.2 在 Service 中使用

```python
from backend.utils.cache_aside import cache_aside_get, cache_aside_invalidate
from backend.services.cache_service import CacheService


class ConfigService:
    def __init__(self, db: AsyncSession, cache: CacheService) -> None:
        self.db = db
        self.cache = cache

    async def get_platform_list(self) -> list:
        return await cache_aside_get(
            key="config:platforms",
            fetcher=self._fetch_platforms,
            cache_service=self.cache,
            l1_ttl=300,
            l2_ttl=600,
        )

    async def update_platform(self, platform_id: int, data: dict) -> None:
        # ... update DB ...
        await cache_aside_invalidate("config:platforms", self.cache)

    async def _fetch_platforms(self) -> list:
        result = await self.db.execute(select(DimPlatform))
        return [row.name for row in result.scalars().all()]
```

---

## 7. 乐观锁模式

通过 `version` 字段防止并发更新冲突。

### 7.1 ORM 模型定义

```python
# modules/core/db/schema.py (已有模式)
class MyTable(Base):
    __tablename__ = "my_table"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
```

### 7.2 Service 层版本检查

```python
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.base_crud import OptimisticLockError
from modules.core.db import MyTable


async def update_with_lock(
    db: AsyncSession,
    item_id: int,
    new_name: str,
    expected_version: int,
) -> MyTable:
    """
    Optimistic lock update:
    WHERE id = :id AND version = :expected_version
    """
    result = await db.execute(
        update(MyTable)
        .where(MyTable.id == item_id, MyTable.version == expected_version)
        .values(name=new_name, version=expected_version + 1)
        .returning(MyTable)
    )
    row = result.scalar_one_or_none()

    if row is None:
        raise OptimisticLockError("MyTable", item_id)

    return row
```

### 7.3 Router 层异常处理

```python
from fastapi import HTTPException, status
from backend.services.base_crud import OptimisticLockError


@router.put("/items/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: int,
    payload: ItemUpdate,
    service: MyFeatureService = Depends(get_service),
) -> ItemResponse:
    try:
        item = await service.update(
            item_id,
            payload,
            expected_version=payload.version,
        )
    except OptimisticLockError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Record has been modified by another user. Please refresh and retry.",
        )
    if item is None:
        raise HTTPException(status_code=404, detail="Not found")
    return ItemResponse(success=True, data=item)
```

---

## 8. 依赖注入工厂函数模式

标准 `Depends()` 工厂模式，用于服务实例化和测试替换。

### 8.1 通用工厂函数定义（推荐）

```python
# backend/services/base_service.py
from typing import Any, Type, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

ServiceType = TypeVar("ServiceType")


def provide_service(service_cls: Type[ServiceType], *args: Any, **kwargs: Any):
    """
    创建 FastAPI 依赖注入工厂。

    用法示例::

        from backend.services.base_service import provide_service
        from backend.services.hr_income_calculation_service import HRIncomeCalculationService

        hr_income_service_dep = provide_service(HRIncomeCalculationService)

        @router.post("/income/calculate")
        async def calculate_income_c_class(
            ...,
            service: HRIncomeCalculationService = Depends(hr_income_service_dep),
        ):
            result = await service.calculate_month(year_month)
            ...

    这样在测试中可以通过 ``app.dependency_overrides[hr_income_service_dep]`` 注入 mock 实现。
    """
    try:
        from fastapi import Depends as _Depends  # type: ignore
        from backend.models.database import get_async_db as _get_async_db  # type: ignore
    except Exception:  # pragma: no cover - 非 Web 运行环境下跳过
        async def _fallback_dep(*_args: Any, **_kwargs: Any) -> ServiceType:  # type: ignore[return-type]
            return service_cls(*args, **kwargs)  # type: ignore[misc]

        return _fallback_dep

    async def _get_service(
        db: AsyncSession = _Depends(_get_async_db),  # type: ignore[arg-type]
    ) -> ServiceType:
        return service_cls(db, *args, **kwargs)  # type: ignore[misc]

    return _get_service
```

### 8.2 Router 中使用（示例：HR 收入重算）

```python
# backend/routers/hr_employee.py
from backend.services.hr_income_calculation_service import HRIncomeCalculationService
from backend.services.base_service import provide_service

hr_income_service_dep = provide_service(HRIncomeCalculationService)


@router.post("/income/calculate", response_model=IncomeCalculationResponse)
async def calculate_income_c_class(
    year_month: str = Query(..., description="月份(YYYY-MM)"),
    current_user: DimUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
    service: HRIncomeCalculationService = Depends(hr_income_service_dep),
):
    """重算员工收入 C 类表。"""
    try:
        result = await service.calculate_month(year_month)
        return IncomeCalculationResponse(**result)
    except ValueError as e:
        ...
```

### 8.3 测试中 Override（使用 dependency_overrides）

```python
# backend/tests/test_hr_income_di.py
import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.routers import hr_employee


class FakeHRIncomeService:
    async def calculate_month(self, year_month: str) -> dict:
        return {
            "year_month": year_month,
            "total_employees": 0,
            "updated_commissions": 0,
            "updated_performance": 0,
        }


@pytest.mark.asyncio
async def test_calculate_income_uses_overridden_service(auth_headers: dict[str, str]):
    async def _dep_override() -> FakeHRIncomeService:
        return FakeHRIncomeService()

    app.dependency_overrides[hr_employee.hr_income_service_dep] = _dep_override

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://localhost",
        ) as client:
            resp = await client.post(
                "/api/hr/income/calculate",
                params={"year_month": "2025-01"},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["year_month"] == "2025-01"
        assert data["total_employees"] == 0
    finally:
        app.dependency_overrides.pop(hr_employee.hr_income_service_dep, None)
```

---

## 附录: 常见注意事项

| 规则 | 正确做法 | 禁止做法 |
|------|---------|---------|
| 时间戳 | `datetime.now(timezone.utc)` | `datetime.utcnow()` |
| ORM 时间列 | `server_default=func.now()` | `default=datetime.now` |
| DateTime 类型 | `DateTime(timezone=True)` | `DateTime()` |
| Session | `AsyncSession` + `get_async_db()` | `Session` + `get_db()` |
| 查询 | `await db.execute(select(...))` | `db.query(...)` |
| 提交 | `await db.commit()` | `db.commit()` |
| 日志 | `logger.info("[OK] done")` | `logger.info("done")` (无 emoji) |
| Schema 位置 | `backend/schemas/` | `backend/routers/` 中定义 |
| response_model | 必须填写 | 省略 |

---

**最后更新**: 2026-03-16  
**维护**: AI Agent Team  
**状态**: v4.20.0 - 代码模式模板参考文档
