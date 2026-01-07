# Change: 迁移到异步 SQLAlchemy 架构

## Why

当前系统存在**伪异步架构问题**：FastAPI（异步框架）+ SQLAlchemy ORM（同步库）的组合导致：

1. **事件循环阻塞**：在 `async def` 路由/后台任务中使用同步 `db.query()` 会阻塞事件循环
2. **前端无响应**：数据同步期间，其他 API 请求被阻塞，用户界面"转圈"无法操作
3. **并发受限**：即使使用 `asyncio.Semaphore` 控制并发，底层仍是同步阻塞
4. **生产环境风险**：多用户同时操作时，后台同步任务会影响整体系统响应

**问题根源统计**：
- 31 个路由文件中有 **270+ 处** 使用 `get_db` 或 `Session`
- 路由层 **176 处** 同步 `.query()` 调用
- 服务层 **99 处** 同步 `.query()` 调用
- **392 处** `db.commit()/add()/delete()/rollback()` 调用
- **21 处** `SessionLocal()` 直接创建（后台任务中）
- **10 处** `time.sleep()` 阻塞调用

## What Changes

### Phase 1: 核心基础设施（必须）
- [ ] **database.py 异步化**：`create_engine` → `create_async_engine`，`sessionmaker` → `async_sessionmaker`
- [ ] **添加异步依赖**：新增 `asyncpg` 驱动到 `requirements.txt`
- [ ] **异步 get_db 依赖注入**：`get_db()` → `get_async_db()` 返回 `AsyncSession`

### Phase 2: 数据同步模块优先（高影响）
- [ ] **DataSyncService 异步化**：所有方法改为 `async def`，查询改为 `await db.execute(select(...))`
- [ ] **SyncProgressTracker 异步化**：移除 `time.sleep()`，改用 `await asyncio.sleep()`
- [ ] **后台任务函数更新**：`process_batch_sync_background`、`process_single_sync_background` 使用异步会话

### Phase 3: 其他路由模块（渐进式）
- [ ] 按模块优先级迁移 31 个路由文件
- [ ] 按模块优先级迁移 50+ 个服务文件
- [ ] 更新所有 `db.query()` 为 `await db.execute(select())`

### Phase 4: 兼容性保障
- [ ] 保留同步 `engine` 和 `SessionLocal` 用于迁移过渡期
- [ ] 创建迁移脚本自动检测遗漏的同步调用
- [ ] 全面回归测试

## Impact

### 受影响的代码位置

| 类型 | 文件数 | 修改点数 | 优先级 |
|------|--------|---------|--------|
| 核心数据库配置 | 1 | 50+ | P0 |
| 数据同步模块 | 5-10 | 200+ | P0 |
| 其他路由模块 | 25+ | 400+ | P1 |
| 服务层 | 50+ | 500+ | P1 |
| 定时任务 | 3 | 50+ | P2 |

### 性能预期

| 指标 | 当前（同步） | 迁移后（异步） | 提升幅度 |
|------|------------|--------------|---------|
| API 响应时间（同步期间） | 3-10秒 | <100ms | 30-100倍 |
| 并发处理能力 | 受阻塞限制 | 真正并发 | 5-10倍 |
| 系统吞吐量 | 受限 | 大幅提升 | 5-10倍 |
| 多人并发查询 | 串行排队 | 真正并发 | 10-20倍 |
| 连接池利用率 | 低（阻塞浪费） | 高（非阻塞复用） | 5-10倍 |

### 多人并发场景支持

**场景：10 个用户同时操作（查询/上传/下载）**

| 操作类型 | 迁移前 | 迁移后 | 支持情况 |
|---------|--------|--------|---------|
| **查询操作** | 串行执行，总耗时 30-50 秒 | 并发执行，总耗时 5-10 秒 | ✅ 完全支持 |
| **上传操作** | 阻塞其他用户 | 非阻塞，并发处理 | ✅ 基本支持（需优化文件 I/O） |
| **下载操作** | 阻塞其他用户 | 非阻塞，并发处理 | ✅ 完全支持 |
| **数据同步期间** | 所有操作被阻塞 | 其他操作正常响应 | ✅ 完全支持 |

**连接池并发能力**：
- **连接数配置**：`pool_size=30, max_overflow=20`（总计 50 个连接）
- **实际并发能力**：50 个连接可支持 **200-500 个并发请求**（异步复用）
- **原因**：异步连接不阻塞事件循环，连接可快速释放和复用

**性能对比示例**：
```
迁移前（10 用户同时查询）：
- 用户1查询 → 阻塞 3 秒
- 用户2查询 → 等待用户1完成 → 阻塞 3 秒
- ...（串行执行）
- 总耗时：30-50 秒

迁移后（10 用户同时查询）：
- 所有用户查询 → 并发执行
- 总耗时：5-10 秒（最快查询时间）
- 提升：5-10 倍
```

### 风险评估

| 风险 | 严重程度 | 缓解措施 |
|------|---------|---------|
| 迁移期间功能回归 | 高 | 分阶段迁移 + 单元测试 |
| 旧代码兼容性 | 中 | 保留同步接口过渡期 |
| 第三方库兼容性 | 低 | 预先验证依赖兼容性 |

### 依赖变更

**新增**：
- `asyncpg>=0.29.0`（PostgreSQL 异步驱动）
- `aiosqlite>=0.19.0`（SQLite 异步驱动，开发/测试环境）
- `aiofiles>=23.0.0`（推荐：异步文件操作，优化上传/下载性能，避免文件 I/O 阻塞事件循环）

**更新**：
- `sqlalchemy>=2.0.0`（已满足，支持异步）

### 迁移时间估计

| 阶段 | 预计时间 | 说明 |
|------|---------|------|
| Phase 1 | 1天 | 核心基础设施 |
| Phase 2 | 2-3天 | 数据同步模块（高优先） |
| Phase 3 | 3-5天 | 其他模块渐进迁移 |
| Phase 4 | 1-2天 | 兼容性测试和修复 |
| **总计** | **7-11天** | 开发环境完整迁移 |

### 优化建议（迁移后）

#### 1. 文件 I/O 异步化（推荐）

**问题**：文件上传/下载中的同步文件操作可能阻塞事件循环

**解决方案**：
```python
# 使用 aiofiles 进行异步文件操作
import aiofiles

async def save_file_async(file_path: str, data: bytes):
    async with aiofiles.open(file_path, 'wb') as f:
        await f.write(data)

async def read_file_async(file_path: str) -> bytes:
    async with aiofiles.open(file_path, 'rb') as f:
        return await f.read()
```

**影响范围**：
- 文件上传路由（产品图片、Excel 文件等）
- 文件下载路由（报表导出等）
- 日志文件写入（可选优化）

#### 2. 连接池监控（推荐）

**目的**：监控连接池使用情况，根据实际负载调整配置

**实现**：
```python
from backend.models.database import async_engine

@router.get("/health/pool")
async def check_pool_status():
    pool = async_engine.pool
    return {
        "size": pool.size(),
        "checked_out": pool.checkedout(),
        "available": pool.size() - pool.checkedout(),
        "overflow": pool.overflow()
    }
```

**调整建议**：
- 如果 `checked_out` 经常接近 `size`，增加 `pool_size`
- 如果 `overflow` 经常 > 0，增加 `max_overflow`
- 目标：连接池利用率 < 80%

#### 3. CPU 密集型操作处理（可选）

**问题**：图片压缩、Excel 解析等 CPU 密集型操作可能阻塞事件循环

**解决方案**：
```python
# 使用 ProcessPoolExecutor（多进程）
from concurrent.futures import ProcessPoolExecutor

process_executor = ProcessPoolExecutor(max_workers=2)

async def compress_image_async(image_data: bytes):
    loop = asyncio.get_running_loop()  # Python 3.10+ 推荐
    return await loop.run_in_executor(
        process_executor,
        image_processor.compress,
        image_data
    )
```

#### 4. 大文件流式传输（推荐）

**问题**：大文件上传/下载可能占用大量内存

**解决方案**：
```python
# 流式读取，不一次性加载到内存
@router.post("/upload-large")
async def upload_large_file(file: UploadFile):
    async with aiofiles.open(save_path, 'wb') as f:
        while chunk := await file.read(8192):  # 8KB 块
            await f.write(chunk)
```

### 验证标准

**迁移完成后，应满足以下标准**：

| 验证项 | 标准 | 测试方法 |
|-------|------|---------|
| 查询响应时间 | <100ms（即使数据同步进行中） | 压力测试 |
| 多人并发查询 | 10 用户同时查询，总耗时 <10 秒 | 并发测试 |
| 上传/下载不阻塞 | 上传期间其他操作正常响应 | 功能测试 |
| 连接池利用率 | <80%（有足够余量） | 监控接口 |
| 数据同步期间 | 其他 API 响应时间 <100ms | 集成测试 |

