# ExecutorManager 使用指南

v4.19.0 新增：执行器统一管理和资源优化

## 概述

`ExecutorManager` 是系统统一的执行器管理器，负责管理进程池和线程池，确保 CPU 密集型操作和 I/O 密集型操作在合适的执行器中运行，完全隔离事件循环。

## 核心功能

1. **统一管理**：所有执行器由 `ExecutorManager` 统一管理，避免分散创建
2. **环境感知**：根据环境（开发/生产）和 CPU 核心数自动调整资源配置
3. **完全隔离**：CPU 密集型操作在进程池中执行，完全隔离事件循环
4. **优雅关闭**：应用关闭时等待任务完成，确保数据不丢失

## 基本使用

### 导入 ExecutorManager

```python
from backend.services.executor_manager import get_executor_manager
```

### CPU 密集型操作

**适用场景**：
- Excel 文件读取（`ExcelParser.read_excel`）
- 数据计算和处理
- 图片处理
- 其他 CPU 密集型任务

**使用示例**：

```python
from backend.services.executor_manager import get_executor_manager
from backend.services.excel_parser import ExcelParser

executor_manager = get_executor_manager()

# Excel 读取（CPU 密集型）
df = await executor_manager.run_cpu_intensive(
    ExcelParser.read_excel,
    file_path,
    header=header_row,  # ⭐ 使用关键字参数
    nrows=100
)
```

**注意事项**：
- 函数和参数必须可被 `pickle` 序列化
- 如果序列化失败，会抛出 `ValueError` 异常，包含详细错误信息
- 使用关键字参数，确保参数传递正确

### I/O 密集型操作

**适用场景**：
- 文件系统操作（`Path().exists()`, `Path().stat()`）
- 网络请求
- 数据库批量操作（同步模式）
- 其他 I/O 密集型任务

**使用示例**：

```python
from backend.services.executor_manager import get_executor_manager
from pathlib import Path

executor_manager = get_executor_manager()

# 文件系统检查（I/O 密集型）
file_exists = await executor_manager.run_io_intensive(
    lambda: Path(file_path).exists()
)

# 文件大小获取（I/O 密集型）
file_size = await executor_manager.run_io_intensive(
    lambda: Path(file_path).stat().st_size
)
```

## 配置说明

### 环境变量配置

```bash
# 进程池大小（CPU 密集型操作）
# 默认：max(1, CPU核心数 - 1)
# 示例：16核服务器 → 15个进程
CPU_EXECUTOR_WORKERS=15

# 线程池大小（I/O 密集型操作）
# 默认：min(CPU核心数 * 5, 20)
# 示例：16核服务器 → 20个线程（上限）
IO_EXECUTOR_WORKERS=20
```

### Docker 容器配置

在 Docker 容器中，如果设置了 CPU 限制，建议手动设置进程池大小：

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

### 配置优先级

1. **环境变量**：`CPU_EXECUTOR_WORKERS` / `IO_EXECUTOR_WORKERS`（最高优先级）
2. **自动检测**：根据 `os.cpu_count()` 自动计算（默认）

## 错误处理

### 序列化错误

如果函数或参数无法序列化，`run_cpu_intensive` 会抛出 `ValueError`：

```python
try:
    df = await executor_manager.run_cpu_intensive(
        ExcelParser.read_excel,
        file_path,
        header=header_row
    )
except ValueError as e:
    # 序列化失败
    logger.error(f"进程池执行失败: {e}")
    # 可以降级到线程池（如果需要）
    # df = await executor_manager.run_io_intensive(ExcelParser.read_excel, ...)
```

### 执行错误

如果任务执行过程中出错，异常会被传播：

```python
try:
    result = await executor_manager.run_cpu_intensive(func, *args, **kwargs)
except Exception as e:
    # 处理执行错误
    logger.error(f"任务执行失败: {e}")
```

## 最佳实践

### 1. 选择合适的执行器

- **CPU 密集型**：使用 `run_cpu_intensive()`（进程池）
- **I/O 密集型**：使用 `run_io_intensive()`（线程池）

### 2. 使用关键字参数

```python
# ✅ 正确：使用关键字参数
df = await executor_manager.run_cpu_intensive(
    ExcelParser.read_excel,
    file_path,
    header=header_row,  # 关键字参数
    nrows=100
)

# ❌ 错误：使用位置参数（可能导致参数传递错误）
df = await executor_manager.run_cpu_intensive(
    ExcelParser.read_excel,
    file_path,
    header_row,  # 位置参数（不推荐）
    100
)
```

### 3. 确保函数可序列化

如果函数无法序列化，可以创建包装函数：

```python
# 模块级函数（可序列化）
def _read_excel_wrapper(file_path: str, header: int, nrows: int):
    """包装函数，确保可序列化"""
    return ExcelParser.read_excel(file_path, header=header, nrows=nrows)

# 使用包装函数
df = await executor_manager.run_cpu_intensive(
    _read_excel_wrapper,
    file_path,
    header_row,
    100
)
```

### 4. 避免在进程池中使用闭包

```python
# ❌ 错误：闭包无法序列化
def process_data(data):
    def inner_func():
        return data * 2  # 闭包
    return executor_manager.run_cpu_intensive(inner_func)

# ✅ 正确：传递数据作为参数
def process_data(data):
    def inner_func(value):
        return value * 2
    return executor_manager.run_cpu_intensive(inner_func, data)
```

## 性能优化建议

### 1. 限制读取行数

对于大文件，限制读取行数可以显著提升性能：

```python
# 只读取前100行（用于预览）
df = await executor_manager.run_cpu_intensive(
    ExcelParser.read_excel,
    file_path,
    header=header_row,
    nrows=100  # 限制行数
)
```

### 2. 批量处理

对于多个文件，可以并发处理：

```python
# 并发处理多个文件
tasks = [
    executor_manager.run_cpu_intensive(
        ExcelParser.read_excel,
        file_path,
        header=header_row
    )
    for file_path in file_paths
]
results = await asyncio.gather(*tasks)
```

## 监控和调试

### 查看执行器统计

通过资源监控 API 查看执行器状态：

```bash
# 获取执行器统计信息（需要管理员权限）
GET /api/system/executor-stats
```

响应示例：

```json
{
  "cpu_executor": {
    "max_workers": 15,
    "active_tasks": "N/A"
  },
  "io_executor": {
    "max_workers": 20,
    "active_tasks": "N/A"
  }
}
```

### 查看资源使用情况

```bash
# 获取资源使用情况（需要管理员权限）
GET /api/system/resource-usage
```

响应示例：

```json
{
  "cpu_usage": 45.2,
  "memory_usage": 62.5,
  "process_count": 156,
  "thread_count": 42
}
```

## 常见问题

### Q: 为什么 Excel 读取要使用进程池？

A: Excel 读取是 CPU 密集型操作，使用进程池可以完全隔离事件循环，避免阻塞主线程。即使多个文件同时同步，事件循环仍然保持响应。

### Q: 如何知道函数是否可以序列化？

A: 可以运行以下测试：

```python
import pickle
from backend.services.excel_parser import ExcelParser

# 测试序列化
try:
    pickle.dumps(ExcelParser.read_excel)
    print("✅ 可以序列化")
except Exception as e:
    print(f"❌ 无法序列化: {e}")
```

### Q: 进程池大小如何计算？

A: 默认使用 `max(1, CPU核心数 - 1)`，为主进程预留 1 核。例如：
- 16 核服务器 → 15 个进程
- 8 核服务器 → 7 个进程
- 2 核服务器 → 1 个进程

### Q: 如何调整进程池大小？

A: 通过环境变量 `CPU_EXECUTOR_WORKERS` 手动设置：

```bash
export CPU_EXECUTOR_WORKERS=10
```

### Q: Docker 容器中如何配置？

A: 如果容器设置了 CPU 限制，建议手动设置：

```yaml
environment:
  CPU_EXECUTOR_WORKERS: 1  # 容器限制2 CPU，使用1个进程
```

## 相关文档

- [执行器统一管理和资源优化提案](../../openspec/changes/optimize-executor-resource-management/proposal.md)
- [系统资源监控 API 文档](#系统资源监控)
- [数据库连接池配置指南](#数据库连接池)

