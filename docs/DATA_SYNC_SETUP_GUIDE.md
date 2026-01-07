# 数据同步功能设置指南

**版本**: v4.12.1  
**更新日期**: 2025-11-18

---

## 📋 前置要求

### 1. 依赖安装

```bash
# 安装Celery和Redis客户端
pip install celery>=5.3.0 redis>=5.0.0
```

### 2. Redis服务

Redis用于Celery的消息队列和结果存储。

#### 方式1：使用Docker（推荐）

```bash
# 启动Redis容器
docker-compose up -d redis

# 或使用docker命令
docker run -d --name xihong_erp_redis -p 6379:6379 redis:alpine
```

#### 方式2：使用本地Redis服务

如果已安装Redis，直接启动：
```bash
# Linux/Mac
redis-server

# Windows（如果已安装）
redis-server.exe
```

#### 方式3：使用云Redis服务

修改`.env`文件中的`CELERY_BROKER_URL`和`CELERY_RESULT_BACKEND`配置。

---

## 🚀 启动步骤

### 1. 启动Redis

**Windows**:
```bash
# 使用Docker Compose（推荐）
docker-compose up -d redis

# 或使用启动脚本
scripts\start_redis_and_celery.bat
```

**Linux/Mac**:
```bash
# 使用Docker Compose（推荐）
docker-compose up -d redis

# 或使用启动脚本
chmod +x scripts/start_redis_and_celery.sh
./scripts/start_redis_and_celery.sh
```

### 2. 验证Redis连接

```bash
python -c "import redis; r = redis.Redis(host='localhost', port=6379, db=0); r.ping(); print('Redis连接成功')"
```

### 3. 启动Celery Worker

**Windows**:
```bash
# 在新终端窗口运行
celery -A backend.celery_app worker --loglevel=info --queues=data_sync --pool=solo
```

**Linux/Mac**:
```bash
# 在新终端窗口运行
celery -A backend.celery_app worker --loglevel=info --queues=data_sync
```

**或使用启动脚本**（自动启动Redis和Celery）:
```bash
# Windows
scripts\start_redis_and_celery.bat

# Linux/Mac
chmod +x scripts/start_redis_and_celery.sh
./scripts/start_redis_and_celery.sh
```

---

## 🧪 测试功能

### 1. 测试Redis连接

```bash
python scripts/test_data_sync_improvements.py
```

### 2. 测试API

```bash
# 批量同步（异步）
curl -X POST http://localhost:8001/api/data-sync/batch \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "shopee",
    "domains": ["orders"],
    "limit": 10,
    "only_with_template": true,
    "allow_quarantine": true
  }'

# 查询进度
curl http://localhost:8001/api/data-sync/progress/{task_id}
```

### 3. 查看Celery任务状态

```bash
# 查看活跃任务
celery -A backend.celery_app inspect active

# 查看注册的任务
celery -A backend.celery_app inspect registered

# 查看Worker状态
celery -A backend.celery_app inspect stats
```

---

## ⚙️ 配置说明

### 环境变量

在`.env`文件中配置：

```env
# Celery配置
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Redis配置（如果使用Docker）
REDIS_PORT=6379
```

### Celery Worker配置

**并发数配置**（`backend/celery_app.py`）:
```python
worker_concurrency=4  # 并发worker数量
```

**队列配置**:
- `data_sync`: 数据同步任务队列
- `data_processing`: 数据处理任务队列
- `scheduled`: 定时任务队列

---

## 🔧 故障排除

### 问题1: Redis连接失败

**症状**: `ConnectionError: Error 10061 connecting to localhost:6379`

**解决方案**:
1. 检查Redis是否运行: `docker ps --filter "name=redis"`
2. 检查端口是否被占用: `netstat -an | findstr :6379`
3. 重启Redis: `docker-compose restart redis`

### 问题2: Celery Worker无法启动

**症状**: `ModuleNotFoundError: No module named 'celery'`

**解决方案**:
```bash
pip install celery redis
```

### 问题3: 任务未执行

**症状**: 任务提交成功，但未执行

**解决方案**:
1. 检查Celery Worker是否运行: `celery -A backend.celery_app inspect active`
2. 检查队列名称是否正确: `--queues=data_sync`
3. 查看Worker日志: 检查Celery Worker输出

### 问题4: Docker镜像拉取失败

**症状**: `failed to resolve reference "docker.io/library/redis:alpine"`

**解决方案**:
1. 检查网络连接
2. 尝试使用其他镜像源
3. 手动拉取镜像: `docker pull redis:alpine`
4. 或使用本地Redis服务

---

## 📊 监控和日志

### Celery Worker日志

Celery Worker会在终端输出详细日志，包括：
- 任务接收和执行状态
- 错误信息
- 性能统计

### Redis监控

```bash
# 连接Redis CLI
docker exec -it xihong_erp_redis redis-cli

# 查看键
KEYS *

# 查看队列长度
LLEN celery
```

### 任务进度查询

通过API查询任务进度：
```bash
GET /api/data-sync/progress/{task_id}
```

---

## ✅ 验证清单

- [ ] Redis服务已启动并可以连接
- [ ] Celery已安装（`pip install celery redis`）
- [ ] Celery Worker已启动（`celery -A backend.celery_app worker --queues=data_sync`）
- [ ] 后端API服务已启动（`python run.py`）
- [ ] 测试脚本通过（`python scripts/test_data_sync_improvements.py`）

---

## 📚 相关文档

- [数据同步改进功能实施报告](docs/DATA_SYNC_IMPROVEMENTS_IMPLEMENTATION_REPORT.md)
- [企业级ERP标准合规性评估](docs/DATA_SYNC_ERP_COMPLIANCE_ASSESSMENT.md)
- [数据同步架构设计](docs/DATA_SYNC_ARCHITECTURE.md)

---

**最后更新**: 2025-11-18  
**维护者**: AI Agent

