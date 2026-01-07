# 资源配置指南

v4.19.0 新增：执行器统一管理和资源优化

## 概述

本文档说明如何配置系统资源（执行器、数据库连接池等），以优化性能和成本。

## 执行器配置

### 进程池配置（CPU 密集型操作）

**默认配置**：
- 公式：`max(1, CPU核心数 - 1)`
- 示例：
  - 16 核服务器 → 15 个进程
  - 8 核服务器 → 7 个进程
  - 4 核服务器 → 3 个进程
  - 2 核服务器 → 1 个进程

**环境变量**：
```bash
# 手动设置进程池大小
export CPU_EXECUTOR_WORKERS=15
```

**Docker 容器配置**：
```yaml
# docker-compose.yml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '2'
    environment:
      # 手动设置进程池大小（2 CPU - 1 = 1个进程）
      CPU_EXECUTOR_WORKERS: 1
```

### 线程池配置（I/O 密集型操作）

**默认配置**：
- 公式：`min(CPU核心数 * 5, 20)`
- 示例：
  - 16 核服务器 → 20 个线程（上限）
  - 8 核服务器 → 20 个线程（上限）
  - 4 核服务器 → 20 个线程（上限）
  - 2 核服务器 → 10 个线程

**环境变量**：
```bash
# 手动设置线程池大小
export IO_EXECUTOR_WORKERS=20
```

## 数据库连接池配置

### 生产环境

**默认配置**（根据 CPU 核心数自动计算）：
- 基础连接池：`min(30, CPU核心数 * 10)`
- 溢出连接数：`min(20, CPU核心数 * 5)`

**环境变量**：
```bash
# 手动设置连接池大小
export DB_POOL_SIZE=30
export DB_MAX_OVERFLOW=20
```

### 开发环境

**默认配置**（固定较小值）：
- 基础连接池：10
- 溢出连接数：10

**说明**：开发环境使用较小值，节省数据库资源。

## 资源监控配置

### 告警阈值

**默认配置**：
- CPU 使用率阈值：80%
- 内存使用率阈值：85%
- 检查间隔：60 秒

**环境变量**：
```bash
# 自定义告警阈值
export RESOURCE_MONITOR_CPU_THRESHOLD=80.0
export RESOURCE_MONITOR_MEMORY_THRESHOLD=85.0
export RESOURCE_MONITOR_CHECK_INTERVAL=60

# 禁用资源监控
export RESOURCE_MONITOR_ENABLED=false
```

## 完整配置示例

### 生产环境（16 核服务器）

```bash
# 执行器配置
export CPU_EXECUTOR_WORKERS=15  # 16 - 1 = 15
export IO_EXECUTOR_WORKERS=20   # min(16 * 5, 20) = 20

# 数据库连接池配置
export DB_POOL_SIZE=30          # min(30, 16 * 10) = 30
export DB_MAX_OVERFLOW=20       # min(20, 16 * 5) = 20

# 资源监控配置
export RESOURCE_MONITOR_CPU_THRESHOLD=80.0
export RESOURCE_MONITOR_MEMORY_THRESHOLD=85.0
export RESOURCE_MONITOR_CHECK_INTERVAL=60
export RESOURCE_MONITOR_ENABLED=true

# 环境标识
export ENVIRONMENT=production
```

### 开发环境（8 核开发机）

```bash
# 执行器配置（充分利用开发电脑性能）
export CPU_EXECUTOR_WORKERS=7   # 8 - 1 = 7
export IO_EXECUTOR_WORKERS=20   # min(8 * 5, 20) = 20

# 数据库连接池配置（节省数据库资源）
export DB_POOL_SIZE=10          # 开发环境固定值
export DB_MAX_OVERFLOW=10       # 开发环境固定值

# 资源监控配置（可选）
export RESOURCE_MONITOR_ENABLED=false  # 开发环境可禁用

# 环境标识
export ENVIRONMENT=development
```

### Docker 容器配置

```yaml
# docker-compose.yml
services:
  backend:
    image: xihong-erp-backend:latest
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
    environment:
      # 执行器配置（根据容器CPU限制）
      CPU_EXECUTOR_WORKERS: 1  # 2 - 1 = 1
      IO_EXECUTOR_WORKERS: 10  # min(2 * 5, 20) = 10
      
      # 数据库连接池配置
      DB_POOL_SIZE: 10
      DB_MAX_OVERFLOW: 10
      
      # 资源监控配置
      RESOURCE_MONITOR_CPU_THRESHOLD: 80.0
      RESOURCE_MONITOR_MEMORY_THRESHOLD: 85.0
      RESOURCE_MONITOR_CHECK_INTERVAL: 60
      RESOURCE_MONITOR_ENABLED: true
      
      # 环境标识
      ENVIRONMENT: production
```

## 性能调优建议

### 1. 高并发场景

如果系统需要处理大量并发请求，可以适当增加线程池大小：

```bash
export IO_EXECUTOR_WORKERS=30  # 超过默认上限20
```

### 2. CPU 密集型任务较多

如果系统主要处理 CPU 密集型任务，可以适当增加进程池大小（但不超过 CPU 核心数）：

```bash
# 16核服务器，如果主要处理CPU密集型任务
export CPU_EXECUTOR_WORKERS=16  # 使用全部核心（不推荐，建议保留1核）
```

### 3. 内存受限环境

如果系统内存受限，可以减少进程池大小：

```bash
# 内存受限，减少进程数
export CPU_EXECUTOR_WORKERS=4  # 减少进程数，降低内存占用
```

## 监控和调试

### 查看当前配置

通过资源监控 API 查看当前配置：

```bash
# 获取执行器统计信息（需要管理员权限）
curl -H "Authorization: Bearer <token>" \
  http://localhost:8001/api/system/executor-stats

# 响应示例
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
curl -H "Authorization: Bearer <token>" \
  http://localhost:8001/api/system/resource-usage

# 响应示例
{
  "cpu_usage": 45.2,
  "memory_usage": 62.5,
  "process_count": 156,
  "thread_count": 42
}
```

### 查看数据库连接池状态

```bash
# 获取数据库连接池统计（需要管理员权限）
curl -H "Authorization: Bearer <token>" \
  http://localhost:8001/api/system/db-pool-stats

# 响应示例
{
  "sync_pool": {
    "size": 30,
    "checked_out": 5,
    "overflow": 0
  },
  "async_pool": {
    "size": 30,
    "checked_out": 3,
    "overflow": 0
  }
}
```

## 常见问题

### Q: 如何知道当前使用了多少资源？

A: 通过资源监控 API 查看：
- `/api/system/resource-usage` - 系统资源使用情况
- `/api/system/executor-stats` - 执行器配置和状态
- `/api/system/db-pool-stats` - 数据库连接池状态

### Q: Docker 容器中如何正确配置？

A: 如果容器设置了 CPU 限制，建议手动设置 `CPU_EXECUTOR_WORKERS`：

```yaml
environment:
  CPU_EXECUTOR_WORKERS: 1  # 容器限制2 CPU，使用1个进程
```

### Q: 如何优化性能？

A: 根据实际负载调整：
- **高并发场景**：增加 `IO_EXECUTOR_WORKERS`
- **CPU 密集型任务多**：确保 `CPU_EXECUTOR_WORKERS` 足够（但不超过 CPU 核心数）
- **内存受限**：减少 `CPU_EXECUTOR_WORKERS`（进程占用更多内存）

### Q: 如何禁用资源监控？

A: 设置环境变量：

```bash
export RESOURCE_MONITOR_ENABLED=false
```

## 相关文档

- [ExecutorManager 使用指南](../guides/EXECUTOR_MANAGER_GUIDE.md)
- [执行器统一管理和资源优化提案](../../openspec/changes/optimize-executor-resource-management/proposal.md)

