# Design: 迁移到异步 SQLAlchemy 架构

## Context

### 背景
当前西虹 ERP 系统使用 FastAPI（异步框架）+ SQLAlchemy ORM（同步库）的组合。这种架构在简单场景下工作正常，但在长时间运行的数据同步任务中会阻塞事件循环，导致前端无响应。

### 约束条件
1. 必须保持现有 API 契约不变
2. 需要最小化对现有代码的修改
3. 需要支持渐进式迁移（不能一次性全部修改）
4. 需要保持向后兼容（过渡期）

### 利益相关者
- 开发团队：需要学习异步 SQLAlchemy 模式
- 用户：期望系统响应性提升
- 运维：需要更新部署配置（新依赖）

## Goals / Non-Goals

### Goals
- 实现真正的异步数据库操作，消除事件循环阻塞
- 提升系统并发处理能力
- 确保数据同步期间其他模块可正常操作
- 提供清晰的迁移路径和工具

### Non-Goals
- 不修改现有 API 契约（请求/响应格式不变）
- 不迁移到其他 ORM（如 Tortoise ORM、SQLModel）
- 不引入复杂的缓存层（Redis 等）
- 不修改数据库 Schema

## Decisions

### Decision 1: 使用 SQLAlchemy 2.0 异步模式

**选择**：使用 `sqlalchemy.ext.asyncio` 模块

**原因**：
- SQLAlchemy 2.0 原生支持异步，无需迁移到其他 ORM
- 查询语法变化小（`db.query()` → `await db.execute(select())`）
- 团队已熟悉 SQLAlchemy

**替代方案**：
| 方案 | 优点 | 缺点 | 决策 |
|------|-----|-----|------|
| SQLAlchemy Async | 原生支持，变化小 | 需要更新查询语法 | ✅ 选择 |
| Tortoise ORM | 设计上异步优先 | 完全重写，学习曲线高 | ❌ 拒绝 |
| SQLModel | Pydantic 集成好 | 相对较新，生态小 | ❌ 拒绝 |
| ThreadPoolExecutor 包装 | 无需修改查询 | 性能提升有限，复杂度高 | ❌ 拒绝 |

### Decision 2: 使用 asyncpg 驱动

**选择**：使用 `asyncpg` 作为 PostgreSQL 异步驱动

**原因**：
- 性能最佳的 PostgreSQL 异步驱动
- SQLAlchemy 官方推荐
- 社区活跃，稳定性高

**连接字符串变化**：
```python
# 同步
DATABASE_URL = "postgresql://user:pass@host/db"
# 或
DATABASE_URL = "postgresql+psycopg2://user:pass@host/db"

# 异步（使用转换函数）
from urllib.parse import urlparse, urlunparse

def get_async_database_url(database_url: str) -> str:
    """
    将同步数据库URL转换为异步URL（健壮处理）
    
    支持的数据库类型：
    - PostgreSQL: postgresql:// → postgresql+asyncpg://
    - SQLite: sqlite:// → sqlite+aiosqlite://
    """
    parsed = urlparse(database_url)
    scheme = parsed.scheme.split('+')[0]  # 移除现有驱动（如 +psycopg2）
    
    # 根据数据库类型选择异步驱动
    if scheme == "postgresql":
        new_scheme = "postgresql+asyncpg"
    elif scheme == "sqlite":
        new_scheme = "sqlite+aiosqlite"
    else:
        raise ValueError(f"不支持的数据库类型: {scheme}")
    
    new_parsed = parsed._replace(scheme=new_scheme)
    return urlunparse(new_parsed)  # 保留所有查询参数

ASYNC_DATABASE_URL = get_async_database_url(DATABASE_URL)
# PostgreSQL 结果: "postgresql+asyncpg://user:pass@host/db"
# SQLite 结果: "sqlite+aiosqlite:///path/to/db.sqlite"
```

### Decision 3: 渐进式迁移策略

**选择**：分阶段迁移，保持同步/异步双模式共存

**迁移顺序**：
1. Phase 1：核心数据库配置（`backend/models/database.py`）
2. Phase 2：数据同步模块（影响最大，优先解决）
3. Phase 3：其他模块（按优先级渐进）
4. Phase 4：清理同步接口

**共存模式**：
```python
# backend/models/database.py

# === 同步模式（过渡期保留） ===
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# === 异步模式（新代码使用） ===
async_engine = create_async_engine(ASYNC_DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(bind=async_engine, expire_on_commit=False)

async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    异步数据库会话依赖注入
    
    ⚠️ 事务策略说明：
    - 成功时自动 commit（请求结束后）
    - 异常时自动 rollback
    - 如果路由函数内已手动 commit，此处再次 commit 是无害的（空操作）
    
    推荐做法：
    - 对于只读操作：无需手动 commit
    - 对于写操作：可以依赖自动 commit，或手动 commit 以明确控制点
    - 对于需要精确控制的场景：使用 `async with session.begin():` 显式事务
    """
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()  # 自动提交（如果有未提交的更改）
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()

# === 替代方案：不自动提交（需路由函数自行管理） ===
async def get_async_db_no_autocommit() -> AsyncGenerator[AsyncSession, None]:
    """
    不自动提交的会话（需调用者显式 commit）
    
    适用场景：
    - 需要精确控制事务边界
    - 复杂的多步骤操作
    """
    session = AsyncSessionLocal()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
```

### Decision 4: 查询语法迁移模式

**同步查询 → 异步查询对照表**：

| 同步模式 | 异步模式 |
|---------|---------|
| `db.query(Model).all()` | `result = await db.execute(select(Model)); result.scalars().all()` |
| `db.query(Model).filter(...).first()` | `result = await db.execute(select(Model).where(...)); result.scalar_one_or_none()` |
| `db.query(Model).filter(...).count()` | `result = await db.execute(select(func.count()).select_from(Model).where(...)); result.scalar()` |
| `db.add(obj)` | `session.add(obj)` (无需 await) |
| `db.commit()` | `await session.commit()` |
| `db.rollback()` | `await session.rollback()` |
| `db.refresh(obj)` | `await session.refresh(obj)` |
| `db.delete(obj)` | `await session.delete(obj)` |
| 显式事务管理 | `async with session.begin(): ...` (自动提交/回滚) |

### Decision 5: 后台任务会话管理

**选择**：每个后台任务/协程创建独立的异步会话

⚠️ **重要**：`async_sessionmaker` 创建的会话**不是上下文管理器**，不能使用 `async with AsyncSessionLocal() as session`。必须手动管理生命周期。

**正确模式**：
```python
async def process_batch_sync_background(file_ids: List[int], ...):
    # ⭐ 正确：手动创建和关闭会话
    db_main = AsyncSessionLocal()
    try:
        progress_tracker = SyncProgressTracker(db_main)
        
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def sync_single(file_id: int):
            async with semaphore:
                # ⭐ 每个协程独立会话（手动管理）
                db = AsyncSessionLocal()
                try:
                    sync_service = DataSyncService(db)
                    result = await sync_service.sync_single_file(file_id)
                    await db.commit()
                    return result
                except Exception as e:
                    await db.rollback()
                    raise
                finally:
                    await db.close()
        
        tasks = [sync_single(fid) for fid in file_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        await db_main.commit()
    except Exception:
        await db_main.rollback()
        raise
    finally:
        await db_main.close()
```

**替代方案（使用显式事务）**：
```python
async def sync_single(file_id: int):
    async with semaphore:
        db = AsyncSessionLocal()
        try:
            async with db.begin():  # 自动提交/回滚
                sync_service = DataSyncService(db)
                return await sync_service.sync_single_file(file_id)
        finally:
            await db.close()
```

## Risks / Trade-offs

### Risk 1: 迁移期间功能回归
**严重程度**：高
**缓解措施**：
- 分阶段迁移，每阶段完成后测试
- 保留同步接口作为回退选项
- 充分的单元测试和集成测试

### Risk 2: 学习曲线
**严重程度**：中
**缓解措施**：
- 提供查询语法对照表
- 创建代码模板和示例
- 更新开发规范文档

### Risk 3: 第三方库兼容性
**严重程度**：低
**缓解措施**：
- 预先验证所有依赖库的异步兼容性
- 必要时使用 `run_in_executor` 包装同步调用

### Trade-off: 代码复杂度 vs 性能

**当前（简单但阻塞）**：
```python
async def get_files(db: Session = Depends(get_db)):
    return db.query(CatalogFile).all()  # 简单，但阻塞
```

**迁移后（稍复杂但非阻塞）**：
```python
async def get_files(db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(select(CatalogFile))  # 稍复杂，但非阻塞
    return result.scalars().all()
```

**权衡结论**：代码复杂度轻微增加，但性能提升显著（5-10倍），值得迁移。

## Migration Plan

### 步骤概览

```
+------------------+     +------------------+     +------------------+
|   Phase 1        | --> |   Phase 2        | --> |   Phase 3        |
| 核心基础设施      |     | 数据同步模块      |     | 其他模块         |
| (1天)            |     | (2-3天)          |     | (3-5天)          |
+------------------+     +------------------+     +------------------+
                                                          |
                                                          v
                                              +------------------+
                                              |   Phase 4        |
                                              | 测试与清理       |
                                              | (1-2天)          |
                                              +------------------+
```

### 回滚方案

1. **Phase 1 回滚**：删除异步配置，恢复纯同步模式
2. **Phase 2 回滚**：将数据同步模块回滚到同步版本
3. **Phase 3 回滚**：逐模块回滚
4. **Git 分支策略**：每个 Phase 创建独立分支，合并前验证

### 验证节点

| 节点 | 验证内容 | 通过标准 |
|------|---------|---------|
| Phase 1 完成 | 异步连接池工作正常 | 连接测试通过 |
| Phase 2 完成 | 数据同步不阻塞事件循环 | 同步期间其他 API < 100ms |
| Phase 3 完成 | 所有模块异步化 | 无同步调用遗漏 |
| Phase 4 完成 | 全面测试通过 | 所有测试绿灯 |

## Open Questions

1. **是否需要连接池配置调整？**
   - 当前同步连接池配置：`pool_size=30, max_overflow=70`（总计 100 个连接）
   - **建议异步模式配置**：`pool_size=30, max_overflow=20`（总计 50 个连接）
   - **原因**：异步连接不阻塞事件循环，连接可快速释放和复用，50 个连接可支持 200-500 个并发请求
   - **验证方法**：监控连接池使用率，根据实际负载调整
   - **调整建议**：如果并发请求 > 500，可增加 `pool_size`；如果连接池经常耗尽，可增加 `max_overflow`

2. **Alembic 迁移脚本是否需要异步化？**
   - 目前 Alembic 使用同步模式
   - 迁移脚本通常是一次性运行，可能不需要异步化
   - **建议**：保持同步模式，除非遇到性能问题

3. **测试框架是否需要更新？**
   - pytest-asyncio 已支持异步测试
   - 需要验证现有测试的兼容性

4. **文件 I/O 是否需要异步化？**
   - **当前状态**：文件上传/下载使用 FastAPI 的 `UploadFile` 和 `FileResponse`（部分异步）
   - **建议**：使用 `aiofiles` 进行完全异步的文件操作，避免文件写入阻塞事件循环
   - **影响范围**：文件上传路由、文件下载路由、日志文件写入（可选）

5. **多人并发场景下的性能表现？**
   - **查询操作**：✅ 完全支持，50 个连接可支持 200-500 个并发查询
   - **上传操作**：✅ 基本支持，建议使用 `aiofiles` 优化文件写入
   - **下载操作**：✅ 完全支持，FastAPI 原生支持异步流
   - **数据同步期间**：✅ 完全支持，其他操作不受影响

## Appendix: 代码模板

### 异步路由模板
```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import Depends, HTTPException
from backend.models.database import get_async_db
from backend.utils.api_response import success_response
from modules.core.logger import get_logger

logger = get_logger(__name__)

@router.get("/items")
async def get_items(
    db: AsyncSession = Depends(get_async_db)
):
    try:
        result = await db.execute(select(Item).where(Item.active == True))
        items = result.scalars().all()
        return success_response(data=items)
    except Exception as e:
        logger.error(f"获取items失败: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
```

### 异步服务模板
```python
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from modules.core.logger import get_logger

logger = get_logger(__name__)

class ItemService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_item(self, item_id: int) -> Optional[Item]:
        try:
            result = await self.db.execute(
                select(Item).where(Item.id == item_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"获取item失败: item_id={item_id}, error={e}", exc_info=True)
            await self.db.rollback()
            raise
    
    async def create_item(self, data: ItemCreate) -> Item:
        try:
            item = Item(**data.dict())
            self.db.add(item)
            await self.db.commit()
            await self.db.refresh(item)
            return item
        except Exception as e:
            logger.error(f"创建item失败: {e}", exc_info=True)
            await self.db.rollback()
            raise
    
    # 使用显式事务管理（推荐）
    async def create_item_with_transaction(self, data: ItemCreate) -> Item:
        async with self.db.begin():  # 自动提交/回滚
            item = Item(**data.dict())
            self.db.add(item)
            await self.db.flush()  # 获取ID但不提交
            await self.db.refresh(item)
            return item  # 自动提交
```

### 异步后台任务模板
```python
from typing import List, Dict, Any
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.database import AsyncSessionLocal
from modules.core.logger import get_logger

logger = get_logger(__name__)

async def background_task(item_ids: List[int]) -> List[Dict[str, Any]]:
    """
    后台任务：并发处理多个item
    
    ⚠️ 重要：async_sessionmaker 创建的会话不是上下文管理器，
    必须手动管理生命周期（创建、提交、回滚、关闭）
    """
    # ⭐ 正确：手动创建和管理主会话
    db_main = AsyncSessionLocal()
    try:
        service = ItemService(db_main)
        
        semaphore = asyncio.Semaphore(10)  # 控制并发数
        
        async def process_one(item_id: int) -> Dict[str, Any]:
            """处理单个item（每个协程独立会话）"""
            async with semaphore:
                # ⭐ 正确：手动创建和管理协程会话
                db_local = AsyncSessionLocal()
                try:
                    local_service = ItemService(db_local)
                    result = await local_service.process(item_id)
                    await db_local.commit()
                    return {"success": True, "item_id": item_id, "result": result}
                except Exception as e:
                    logger.error(f"[async] 处理item失败: item_id={item_id}, error={e}", exc_info=True)
                    await db_local.rollback()
                    return {"success": False, "item_id": item_id, "error": str(e)}
                finally:
                    await db_local.close()
        
        # 并发执行所有任务
        tasks = [process_one(item_id) for item_id in item_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常结果
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"[async] 后台任务异常: {result}", exc_info=True)
                processed_results.append({"success": False, "error": str(result)})
            else:
                processed_results.append(result)
        
        await db_main.commit()
        return processed_results
    except Exception as e:
        await db_main.rollback()
        raise
    finally:
        await db_main.close()
```

