# 系统资源监控指南

v4.19.0 新增：执行器统一管理和资源优化

## 概述

系统提供了完整的资源监控功能，包括：
- 实时资源使用情况监控
- 执行器统计信息
- 数据库连接池状态
- 自动资源告警

## API 端点

### 1. 资源使用情况

**端点**: `GET /api/system/resource-usage`

**权限**: 需要管理员权限

**响应示例**:

```json
{
  "cpu_usage": 45.2,
  "memory_usage": 62.5,
  "process_count": 156,
  "thread_count": 42
}
```

**字段说明**:
- `cpu_usage`: CPU 使用率（%）
- `memory_usage`: 内存使用率（%）
- `process_count`: 系统进程数
- `thread_count`: 系统线程数

### 2. 执行器统计信息

**端点**: `GET /api/system/executor-stats`

**权限**: 需要管理员权限

**响应示例**:

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

**字段说明**:
- `cpu_executor.max_workers`: 进程池最大 worker 数
- `cpu_executor.active_tasks`: 活跃任务数（当前无法直接获取，显示 "N/A"）
- `io_executor.max_workers`: 线程池最大 worker 数
- `io_executor.active_tasks`: 活跃任务数（当前无法直接获取，显示 "N/A"）

### 3. 数据库连接池统计

**端点**: `GET /api/system/db-pool-stats`

**权限**: 需要管理员权限

**响应示例**:

```json
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

**字段说明**:
- `sync_pool.size`: 同步连接池大小
- `sync_pool.checked_out`: 已检出的连接数
- `sync_pool.overflow`: 溢出连接数
- `async_pool.size`: 异步连接池大小
- `async_pool.checked_out`: 已检出的连接数
- `async_pool.overflow`: 溢出连接数

## 使用示例

### Python 客户端

```python
import requests

# 获取资源使用情况
response = requests.get(
    "http://localhost:8001/api/system/resource-usage",
    headers={"Authorization": "Bearer <token>"}
)
data = response.json()
print(f"CPU使用率: {data['cpu_usage']}%")
print(f"内存使用率: {data['memory_usage']}%")
```

### JavaScript 客户端

```javascript
// 获取资源使用情况
const response = await fetch('/api/system/resource-usage', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
});
const data = await response.json();
console.log(`CPU使用率: ${data.cpu_usage}%`);
console.log(`内存使用率: ${data.memory_usage}%`);
```

## 资源告警

系统会自动监控资源使用情况，当超过阈值时记录警告日志。

### 告警阈值配置

**环境变量**:

```bash
# CPU 使用率告警阈值（默认：80%）
export RESOURCE_MONITOR_CPU_THRESHOLD=80.0

# 内存使用率告警阈值（默认：85%）
export RESOURCE_MONITOR_MEMORY_THRESHOLD=85.0

# 检查间隔（秒，默认：60）
export RESOURCE_MONITOR_CHECK_INTERVAL=60

# 是否启用监控（默认：true）
export RESOURCE_MONITOR_ENABLED=true
```

### 告警日志示例

当资源使用率超过阈值时，系统会记录警告日志：

```
[ResourceMonitor] [WARN] CPU使用率过高: 85.2% (阈值: 80.0%)
[ResourceMonitor] [WARN] 内存使用率过高: 87.5% (阈值: 85.0%)
[ResourceMonitor] [ERROR] 资源使用率严重超标 - CPU: 85.2%, 内存: 87.5%
```

## 监控最佳实践

### 1. 定期检查

建议定期检查资源使用情况（例如每 5-10 秒）：

```javascript
// 前端轮询示例
setInterval(async () => {
  const data = await fetchResourceUsage();
  updateDashboard(data);
}, 5000);  // 每5秒检查一次
```

### 2. 告警阈值设置

根据实际负载调整告警阈值：

- **开发环境**: 可以设置较高的阈值（如 CPU 90%, 内存 90%）
- **生产环境**: 建议使用默认值（CPU 80%, 内存 85%）

### 3. 性能优化

如果发现资源使用率持续较高：

1. **检查执行器配置**: 确保进程池和线程池大小合理
2. **检查数据库连接池**: 确保连接池大小足够
3. **检查并发任务数**: 考虑限制并发任务数

## 常见问题

### Q: 为什么 `active_tasks` 显示 "N/A"？

A: `ProcessPoolExecutor` 和 `ThreadPoolExecutor` 没有公开 API 获取活跃任务数。如果需要此功能，可以通过跟踪提交的 `Future` 对象来估算（P2 可选功能）。

### Q: 如何禁用资源监控？

A: 设置环境变量：

```bash
export RESOURCE_MONITOR_ENABLED=false
```

### Q: 告警日志在哪里查看？

A: 告警日志会记录到系统日志中，可以通过以下方式查看：

1. **日志文件**: `logs/backend.log`
2. **控制台输出**: 如果启用了控制台日志
3. **日志监控工具**: 如果集成了日志监控系统

## 相关文档

- [ExecutorManager 使用指南](EXECUTOR_MANAGER_GUIDE.md)
- [资源配置指南](../deployment/RESOURCE_CONFIGURATION.md)
- [执行器统一管理和资源优化提案](../../openspec/changes/optimize-executor-resource-management/proposal.md)

