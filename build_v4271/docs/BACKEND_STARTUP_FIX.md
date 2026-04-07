# 后端启动问题修复记录

## 问题描述

后端服务启动时出现Redis连接错误：
```
kombu.exceptions.OperationalError: Error 10061 connecting to localhost:6379
```

## 问题原因

1. **Redis服务未运行**：Celery需要Redis作为消息代理（broker）
2. **错误处理不完善**：代码中只捕获了`ImportError`，没有捕获`OperationalError`（Redis连接失败）

## 修复方案

### 1. 启动Redis服务 ✅

```bash
docker-compose --profile dev up -d redis
```

Redis容器已启动：
- 容器名：`xihong_erp_redis`
- 端口：`6379:6379`
- 状态：healthy

### 2. 添加错误处理 ✅

在所有调用Celery任务的地方添加了完善的错误处理：

**修复的文件**：
- `backend/services/event_listeners.py` - 事件监听器
- `backend/services/data_ingestion_service.py` - 数据入库服务
- `backend/routers/field_mapping.py` - 字段映射API

**错误处理逻辑**：
```python
try:
    # 调用Celery任务
    task.delay(...)
except (ImportError, Exception) as e:
    error_type = type(e).__name__
    if "OperationalError" in error_type or "ConnectionError" in error_type:
        logger.warning(f"Redis/Celery连接失败，使用同步模式（开发模式）")
    else:
        logger.warning(f"任务调用失败: {e}")
    # 降级到同步执行或跳过
```

### 3. 降级策略

当Redis不可用时：
- **事件监听器**：使用同步刷新/计算（开发模式）
- **图片提取任务**：跳过任务，不影响主流程
- **系统继续运行**：核心功能不受影响

## 验证结果

✅ **后端服务已正常启动**
- 健康检查：http://localhost:8001/health - 200 OK
- API文档：http://localhost:8001/api/docs - 可访问
- 281个API端点已注册

✅ **Redis服务已启动**
- 容器状态：healthy
- 连接测试：PONG（正常）

✅ **所有服务运行正常**
- 前端：http://localhost:5173
- 后端：http://localhost:8001
- Metabase：http://localhost:3000
- PostgreSQL：localhost:5432
- Redis：localhost:6379

## 后续建议

### 可选：启动Celery Worker（如果需要异步任务）

如果需要使用Celery异步任务（图片提取、定时任务等），可以启动Celery Worker：

```bash
# 启动Celery Worker
celery -A backend.celery_app worker --loglevel=info

# 启动Celery Beat（定时任务）
celery -A backend.celery_app beat --loglevel=info
```

**注意**：
- Celery Worker是可选的，不影响核心功能
- 系统已配置降级策略，没有Redis也能运行
- 图片提取等任务会跳过，但不影响数据入库

## 相关文档

- `docs/SYSTEM_STARTUP_GUIDE.md` - 系统启动指南
- `backend/celery_app.py` - Celery配置
- `backend/utils/redis_client.py` - Redis客户端（已支持降级）

