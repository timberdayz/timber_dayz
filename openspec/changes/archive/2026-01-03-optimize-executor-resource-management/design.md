# 执行器统一管理和资源优化 - 技术设计文档

## Context

### 背景

当前系统在执行器和资源管理方面存在以下问题：

1. **执行器分散管理**：进程池和线程池分散在多个文件中
2. **资源浪费**：开发环境和生产环境使用相同的资源配置
3. **缺少资源监控**：无法实时了解资源使用情况
4. **CPU密集型操作阻塞**：Excel读取等操作在线程池中执行，仍可能影响事件循环

### 约束条件

- 必须保持向后兼容，不影响现有功能
- 必须支持渐进式迁移
- 必须符合 `.cursorrules` 架构规范
- 必须遵循 SSOT 原则

### 利益相关者

- **开发者**：需要统一的执行器管理，简化代码
- **运维人员**：需要资源监控和自动优化
- **用户**：需要系统响应快速，不阻塞

## Goals / Non-Goals

### Goals

1. **统一执行器管理**：创建 ExecutorManager 统一管理所有执行器
2. **环境感知配置**：根据环境（开发/生产）自动调整资源配置
3. **CPU密集型操作隔离**：将 Excel 读取等操作迁移到进程池，完全隔离
4. **资源监控**：提供实时资源使用情况监控接口
5. **成本优化**：降低开发环境资源消耗，优化生产环境资源利用率

### Non-Goals

1. **不迁移到 Kubernetes**：本次不涉及 Kubernetes 编排和自动扩缩容（已有 docker-compose 支持）
2. **不添加分布式追踪**：本次不涉及 OpenTelemetry 等高级监控
3. **不修改任务队列架构**：数据同步仍使用 `asyncio.create_task()`，不迁移到 Celery
4. **不实现 Docker cgroup 自动检测**：容器 CPU 限制通过环境变量手动配置（未来可优化，P2）

## Decisions

### Decision 1: 使用 ExecutorManager 统一管理执行器

**决策**：创建 `ExecutorManager` 类，统一管理进程池和线程池

**理由**：
- 符合现代化架构标准（统一资源管理）
- 便于监控和调整
- 支持优雅关闭
- 符合 SSOT 原则

**实现**：
```python
import threading
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import asyncio
import os

class ExecutorManager:
    """执行器管理器 - 线程安全的单例模式"""
    _instance = None
    _lock = threading.Lock()
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:  # 双重检查锁定
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # 防止重复初始化
        if ExecutorManager._initialized:
            return
        
        with ExecutorManager._lock:
            if ExecutorManager._initialized:
                return
            
            # ⭐ 初始化logger（必须在所有日志调用之前）
            from modules.core.logger import get_logger
            logger = get_logger(__name__)
            
            # 从环境变量读取配置（支持Docker容器手动设置）
            cpu_cores = os.cpu_count() or 4
            
            # CPU进程池配置（环境变量优先，带验证）
            cpu_workers_env = os.getenv("CPU_EXECUTOR_WORKERS")
            if cpu_workers_env is not None:
                try:
                    cpu_workers = int(cpu_workers_env)
                    if cpu_workers < 0:
                        raise ValueError("CPU_EXECUTOR_WORKERS must be >= 0")
                    if cpu_workers == 0:
                        # 0表示使用默认值
                        cpu_workers = max(1, cpu_cores - 1)
                except ValueError as e:
                    logger.warning(f"Invalid CPU_EXECUTOR_WORKERS: {cpu_workers_env}, using default. Error: {e}")
                    cpu_workers = max(1, cpu_cores - 1)
            else:
                # 自动检测CPU核心数
                # ⭐ 业界常用做法：CPU核心数 - 1（为主进程预留1核）
                cpu_workers = max(1, cpu_cores - 1)
            
            # I/O线程池配置（环境变量优先，带验证）
            io_workers_env = os.getenv("IO_EXECUTOR_WORKERS")
            if io_workers_env is not None:
                try:
                    io_workers = int(io_workers_env)
                    if io_workers < 0:
                        raise ValueError("IO_EXECUTOR_WORKERS must be >= 0")
                    if io_workers == 0:
                        # 0表示使用默认值
                        io_workers = min(cpu_cores * 5, 20)
                except ValueError as e:
                    logger.warning(f"Invalid IO_EXECUTOR_WORKERS: {io_workers_env}, using default. Error: {e}")
                    io_workers = min(cpu_cores * 5, 20)
            else:
                io_workers = min(cpu_cores * 5, 20)
            
            # CPU密集型操作：使用进程池
            self.cpu_executor = ProcessPoolExecutor(
                max_workers=cpu_workers
            )
            
            # I/O密集型操作：使用线程池
            self.io_executor = ThreadPoolExecutor(
                max_workers=io_workers
            )
            
            ExecutorManager._initialized = True
    
    async def run_cpu_intensive(self, func, *args, **kwargs):
        """运行CPU密集型操作（进程池）"""
        import pickle
        from modules.core.logger import get_logger
        
        logger = get_logger(__name__)
        
        try:
            loop = asyncio.get_running_loop()
            # ⚠️ 注意：pickle错误可能在run_in_executor调用时立即抛出（序列化参数时）
            # 也可能在await future时抛出（序列化函数或执行时）
            future = loop.run_in_executor(
                self.cpu_executor,
                func,
                *args,
                **kwargs
            )
            return await future
        except (pickle.PicklingError, AttributeError, TypeError) as e:
            # 如果无法序列化，记录错误并抛出明确的异常
            logger.error(f"无法序列化函数 {func.__name__} 到进程池: {e}")
            raise ValueError(
                f"函数 {func.__name__} 无法在进程池中执行。"
                f"请使用包装函数或确保函数及其参数可被pickle序列化。"
                f"错误详情: {str(e)}"
            ) from e
        except Exception as e:
            # 捕获其他可能的错误（包括进程池执行错误）
            # ⚠️ 注意：可能包括以下异常类型：
            # - BrokenProcessPool: 进程池中的进程崩溃
            # - TimeoutError: 任务执行超时（如果设置了超时）
            # - RuntimeError: 进程池已关闭
            # - 其他执行时异常：函数执行过程中抛出的异常
            logger.error(f"进程池执行失败: {func.__name__}, 错误类型: {type(e).__name__}, 错误: {e}")
            raise
    
    async def run_io_intensive(self, func, *args, **kwargs):
        """运行I/O密集型操作（线程池）"""
        from modules.core.logger import get_logger
        logger = get_logger(__name__)
        
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                self.io_executor,
                func,
                *args,
                **kwargs
            )
        except RuntimeError as e:
            # 线程池已关闭或其他运行时错误
            logger.error(f"线程池执行失败: {func.__name__}, 错误类型: {type(e).__name__}, 错误: {e}")
            raise
        except Exception as e:
            # 捕获其他可能的错误（包括任务执行异常）
            logger.error(f"线程池执行失败: {func.__name__}, 错误类型: {type(e).__name__}, 错误: {e}")
            raise
```

**替代方案考虑**：
- ❌ 继续使用分散的执行器：不符合现代化架构标准
- ❌ 使用 Celery 处理所有任务：增加复杂度，不符合简化原则

### Decision 2: CPU密集型操作迁移到进程池

**决策**：将 Excel 读取等 CPU 密集型操作从线程池迁移到进程池

**理由**：
- 进程池完全隔离，不影响事件循环
- 符合现代化架构最佳实践
- 解决当前阻塞问题

**实现**：
```python
# 之前（线程池）：
df = await loop.run_in_executor(None, ExcelParser.read_excel, ...)

# 现在（进程池）：
executor_manager = get_executor_manager()
df = await executor_manager.run_cpu_intensive(
    ExcelParser.read_excel,
    file_path,
    header=header_row,  # ⭐ 使用关键字参数
    nrows=100  # ⭐ 限制读取行数（可选）
)
```

**替代方案考虑**：
- ❌ 继续使用线程池：仍可能阻塞事件循环
- ❌ 使用独立子进程：增加复杂度，不符合简化原则

### Decision 3: 环境感知的资源配置

**决策**：根据环境（开发/生产）和服务器配置自动调整资源限制

**理由**：
- 开发环境也充分利用硬件性能（开发电脑通常性能很好）
- 生产环境根据服务器配置自动优化
- 支持通过环境变量灵活调整（特别是Docker容器场景）

**实现**：
```python
# backend/utils/config.py
class Settings:
    import os
    cpu_cores = os.cpu_count() or 4
    
    # 优先从环境变量读取（支持Docker容器手动设置）
    # ⚠️ 注意：环境变量为"0"时表示使用默认值，不是0个worker
    cpu_workers_env = os.getenv("CPU_EXECUTOR_WORKERS")
    if cpu_workers_env is not None:
        try:
            cpu_workers = int(cpu_workers_env)
            CPU_EXECUTOR_WORKERS = cpu_workers if cpu_workers > 0 else max(1, cpu_cores - 1)
        except ValueError:
            CPU_EXECUTOR_WORKERS = max(1, cpu_cores - 1)
    else:
        CPU_EXECUTOR_WORKERS = max(1, cpu_cores - 1)
    
    io_workers_env = os.getenv("IO_EXECUTOR_WORKERS")
    if io_workers_env is not None:
        try:
            io_workers = int(io_workers_env)
            IO_EXECUTOR_WORKERS = io_workers if io_workers > 0 else min(cpu_cores * 5, 20)
        except ValueError:
            IO_EXECUTOR_WORKERS = min(cpu_cores * 5, 20)
    else:
        IO_EXECUTOR_WORKERS = min(cpu_cores * 5, 20)
    
    # 根据环境自动调整数据库连接池
    if ENVIRONMENT == "production":
        DB_POOL_SIZE = min(30, cpu_cores * 10)
        DB_MAX_OVERFLOW = min(20, cpu_cores * 5)
    else:
        # 数据库连接池：开发环境使用较小值（节省数据库资源）
        DB_POOL_SIZE = 10
        DB_MAX_OVERFLOW = 10
```

**替代方案考虑**：
- ❌ 固定配置：无法根据环境优化
- ❌ 完全手动配置：增加运维复杂度

### Decision 4: 资源监控接口

**决策**：创建 RESTful API 提供资源使用情况监控

**理由**：
- 实时了解资源使用情况
- 及时发现资源瓶颈
- 为扩容决策提供数据支持

**实现**：
```python
from backend.routers.auth import get_current_user  # ⭐ 导入认证依赖
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials

@router.get("/api/system/resource-usage")
async def get_resource_usage(
    current_user: dict = Depends(get_current_user)  # ⭐ 需要认证
):
    """获取当前资源使用情况（需要管理员权限）"""
    # ⚠️ 建议：仅管理员可访问，避免信息泄露
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    return {
        "cpu_usage": psutil.cpu_percent(interval=0.1),
        "memory_usage": psutil.virtual_memory().percent,
        "process_count": len(psutil.pids()),
        "thread_count": threading.active_count()
    }

@router.get("/api/system/executor-stats")
async def get_executor_stats(
    current_user: dict = Depends(get_current_user)  # ⭐ 需要认证（已导入）
):
    """获取执行器统计信息（需要管理员权限）"""
    # ⚠️ 建议：仅管理员可访问
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    executor_manager = get_executor_manager()
    
    # ⭐ 注意：ProcessPoolExecutor和ThreadPoolExecutor没有公开API获取活跃任务数
    # 可以通过跟踪提交的Future对象来估算（P2可选功能）
    return {
        "cpu_executor": {
            "max_workers": executor_manager.cpu_executor._max_workers,
            "active_tasks": "N/A"  # ⚠️ 无法直接获取，需要额外实现（P2可选）
        },
        "io_executor": {
            "max_workers": executor_manager.io_executor._max_workers,
            "active_tasks": "N/A"  # ⚠️ 无法直接获取，需要额外实现（P2可选）
        }
    }
```

**替代方案考虑**：
- ❌ 使用 Prometheus：增加复杂度，本次不涉及
- ❌ 使用第三方监控服务：增加依赖和成本

## Risks / Trade-offs

### Risk 1: 进程池序列化问题

**风险**：`ExcelParser.read_excel` 可能无法被 pickle 序列化

**缓解措施**：
- 测试 `ExcelParser.read_excel` 是否可序列化
- 如果不可序列化，创建包装函数
- 添加单元测试验证

**影响**：如果无法序列化，需要创建包装函数，增加少量代码

### Risk 2: 资源监控性能开销

**风险**：频繁查询资源使用情况可能影响性能

**缓解措施**：
- 使用轻量级监控（psutil）
- 避免频繁查询（前端轮询间隔 >= 5秒）
- 添加缓存机制（可选）

**影响**：性能开销 <5%，可接受

### Risk 3: 配置错误导致资源耗尽

**风险**：错误的资源配置可能导致资源耗尽

**缓解措施**：
- 使用业界标准公式（CPU核心数 - 1），为主进程预留资源
- 添加配置验证和默认值保护（确保至少1个进程）
- 支持环境变量覆盖（CPU_EXECUTOR_WORKERS）
- 添加资源告警机制

**影响**：通过配置验证和默认值保护，风险可控

### Trade-off 1: 进程池 vs 线程池

**选择**：CPU密集型操作使用进程池

**权衡**：
- ✅ 优点：完全隔离，不影响事件循环
- ⚠️ 缺点：进程间通信有开销，内存占用稍高

**结论**：进程池的隔离优势远大于开销，选择进程池

### Trade-off 2: 统一管理 vs 分散管理

**选择**：统一管理（ExecutorManager）

**权衡**：
- ✅ 优点：便于监控和调整，符合现代化架构
- ⚠️ 缺点：需要修改现有代码

**结论**：统一管理的长期收益大于短期修改成本

## Migration Plan

### Phase 1: 创建 ExecutorManager（不影响现有功能）

1. 创建 `backend/services/executor_manager.py`
2. 在 `backend/main.py` 的 `lifespan` 函数中初始化 ExecutorManager
   - 启动时：调用 `get_executor_manager()` 触发初始化
   - 可选：存储在 `app.state.executor_manager`（便于监控和调试）
   - 关闭时：调用 `await executor_manager.shutdown(timeout=30)`
3. 测试 ExecutorManager 基本功能

### Phase 2: 迁移 CPU 密集型操作（渐进式）

1. 修改 `data_sync_service.py` 中的 Excel 读取
2. 修改 `data_ingestion_service.py` 中的 Excel 读取
3. 测试数据同步功能正常

### Phase 3: 添加资源监控（可选功能）

1. 创建 `backend/routers/system_monitoring.py`
2. 实现监控接口
3. 测试监控接口正常

### Phase 4: 数据库连接池动态调整（优化）

1. 修改 `backend/models/database.py`
2. 测试连接池动态调整正常

### Rollback Plan

如果出现问题，可以：
1. 回滚到使用 `run_in_executor(None, ...)`（线程池）
2. 移除 ExecutorManager，恢复分散管理
3. 所有修改都是渐进式的，可以逐步回滚

## Open Questions

1. **ExcelParser 序列化问题**：需要测试 `ExcelParser.read_excel` 是否可序列化
2. **资源监控频率**：前端轮询间隔应该设置为多少？（建议：5-10秒）
3. **告警阈值**：资源使用率超过多少应该告警？（建议：CPU >80%, 内存 >85%）
4. **进程池大小**：已采用业界标准（CPU核心数 - 1），支持通过环境变量覆盖

## 平台兼容性

### Windows 平台注意事项

**ProcessPoolExecutor 在 Windows 上的行为**：
- Windows 使用 `spawn` 方式创建进程（而非 `fork`）
- 所有传递给进程池的函数和参数必须可被 pickle 序列化
- 在 Windows 上，进程池的性能开销可能略高于 Linux（进程创建开销）
- 进程间通信通过序列化/反序列化，内存占用可能略高

**建议**：
- 确保所有传递给 `run_cpu_intensive()` 的函数和参数可被 pickle 序列化
- 如果遇到序列化问题，考虑使用包装函数或模块级函数
- 在 Windows 上，进程池大小可以适当减小（如果遇到性能问题）

## Docker 容器化支持

### 当前状态

系统已支持 Docker 容器化：
- ✅ PostgreSQL 在 Docker 中运行
- ✅ Metabase 在 Docker 中运行
- ✅ 后端应用支持 Docker 容器化（docker-compose.yml）
- ✅ 前端应用支持 Docker 容器化（docker-compose.yml）

### 容器 CPU 限制处理

**问题**：
- Docker 容器中的 `os.cpu_count()` 可能返回主机 CPU 核心数
- 如果容器设置了 CPU 限制（如 `cpus: '2'`），进程池大小计算可能不准确

**解决方案**：
1. **当前方案**：通过环境变量 `CPU_EXECUTOR_WORKERS` 手动设置
   ```bash
   # docker-compose.yml 中设置
   environment:
     CPU_EXECUTOR_WORKERS: 1  # 容器限制2 CPU，使用1个进程
   ```

2. **未来优化**（P2，可选）：
   - 从 Docker cgroup 读取实际 CPU 限制
   - 自动检测容器资源限制
   - 需要添加 `psutil` 或 `cgroups` 库支持

**示例配置**：
```yaml
# docker-compose.yml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
    environment:
      # 手动设置进程池大小（2 CPU - 1 = 1个进程）
      CPU_EXECUTOR_WORKERS: 1
      ENVIRONMENT: production
```

## Implementation Notes

### 关键实现点

1. **单例模式**：确保 ExecutorManager 只有一个实例（使用双重检查锁定，线程安全）
2. **优雅关闭**：应用关闭时等待任务完成（设置超时，如30秒后强制关闭）
3. **错误处理**：进程池执行失败时的错误处理和重试机制
4. **资源监控**：轻量级监控（使用psutil），避免性能开销
5. **Docker 支持**：支持通过环境变量配置容器资源限制
6. **环境变量优先级**：环境变量 `CPU_EXECUTOR_WORKERS` 优先于自动检测

### 优雅关闭实现

```python
async def shutdown(self, timeout: int = 30):
    """优雅关闭执行器"""
    import asyncio
    import time
    from modules.core.logger import get_logger
    
    logger = get_logger(__name__)
    
    # 使用标志位跟踪关闭请求状态（避免访问私有属性）
    cpu_shutdown_requested = False
    io_shutdown_requested = False
    
    # 关闭进程池（不等待，允许任务继续执行）
    if not cpu_shutdown_requested:
        try:
            self.cpu_executor.shutdown(wait=False)
            cpu_shutdown_requested = True
            logger.info("[ExecutorManager] 进程池关闭请求已发送")
        except Exception as e:
            logger.warning(f"[ExecutorManager] 关闭进程池时出错: {e}")
    
    # 关闭线程池（不等待，允许任务继续执行）
    if not io_shutdown_requested:
        try:
            self.io_executor.shutdown(wait=False)
            io_shutdown_requested = True
            logger.info("[ExecutorManager] 线程池关闭请求已发送")
        except Exception as e:
            logger.warning(f"[ExecutorManager] 关闭线程池时出错: {e}")
    
    # 等待任务完成（最多等待timeout秒）
    # ⚠️ 注意：ProcessPoolExecutor和ThreadPoolExecutor没有公开API检查任务状态
    # 这里只能等待，无法精确判断任务是否完成
    start_time = time.time()
    wait_interval = 0.5  # 每0.5秒检查一次
    
    while (time.time() - start_time) < timeout:
        elapsed = time.time() - start_time
        if elapsed >= timeout * 0.8:  # 80%时间后准备强制关闭
            logger.info(f"[ExecutorManager] 等待时间已过80%({elapsed:.1f}秒)，准备强制关闭")
            break
        await asyncio.sleep(wait_interval)
    
    # 强制关闭（等待剩余任务完成）
    # ⚠️ 注意：即使第一次调用shutdown(wait=False)成功，也需要调用shutdown(wait=True)等待任务完成
    # shutdown()方法是幂等的，可以安全地多次调用
    if cpu_shutdown_requested:
        try:
            logger.info("[ExecutorManager] 等待进程池任务完成...")
            self.cpu_executor.shutdown(wait=True)
            logger.info("[ExecutorManager] 进程池已完全关闭")
        except Exception as e:
            logger.warning(f"[ExecutorManager] 等待进程池关闭时出错: {e}")
    else:
        # 如果第一次调用失败，尝试直接关闭
        try:
            logger.info("[ExecutorManager] 强制关闭进程池（等待任务完成）")
            self.cpu_executor.shutdown(wait=True)
        except Exception as e:
            logger.warning(f"[ExecutorManager] 强制关闭进程池时出错: {e}")
    
    if io_shutdown_requested:
        try:
            logger.info("[ExecutorManager] 等待线程池任务完成...")
            self.io_executor.shutdown(wait=True)
            logger.info("[ExecutorManager] 线程池已完全关闭")
        except Exception as e:
            logger.warning(f"[ExecutorManager] 等待线程池关闭时出错: {e}")
    else:
        # 如果第一次调用失败，尝试直接关闭
        try:
            logger.info("[ExecutorManager] 强制关闭线程池（等待任务完成）")
            self.io_executor.shutdown(wait=True)
        except Exception as e:
            logger.warning(f"[ExecutorManager] 强制关闭线程池时出错: {e}")
    
    logger.info("[ExecutorManager] 所有执行器已关闭")
```

### get_executor_manager 函数实现

```python
def get_executor_manager() -> ExecutorManager:
    """
    获取ExecutorManager单例实例
    
    Returns:
        ExecutorManager: 执行器管理器实例
    """
    return ExecutorManager()
```

### 代码示例

```python
# 使用 ExecutorManager
from backend.services.executor_manager import get_executor_manager

executor_manager = get_executor_manager()

# CPU密集型操作（自动处理序列化错误）
try:
    df = await executor_manager.run_cpu_intensive(
        ExcelParser.read_excel,
        file_path,
        header=header_row,  # ⭐ 使用关键字参数，匹配ExcelParser.read_excel的签名
        nrows=100  # ⭐ 限制读取行数（可选）
    )
except ValueError as e:
    # 如果无法序列化，会抛出明确的错误信息
    logger.error(f"进程池执行失败: {e}")
    # 可以降级到线程池（如果需要）
    # df = await executor_manager.run_io_intensive(ExcelParser.read_excel, ...)

# I/O密集型操作
file_exists = await executor_manager.run_io_intensive(
    lambda: Path(file_path).exists()
)
```

### 测试策略

1. **单元测试**：ExecutorManager 的功能测试
2. **集成测试**：数据同步在进程池中执行的测试
3. **性能测试**：验证事件循环响应时间
4. **压力测试**：验证多人并发场景下的资源使用

