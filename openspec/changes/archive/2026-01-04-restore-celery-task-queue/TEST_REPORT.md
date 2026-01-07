# Celery 任务队列测试报告

**测试日期**: 2026-01-03  
**测试人员**: AI Agent  
**测试环境**: Windows 开发环境

---

## 📋 测试前准备

### 服务状态检查

| 服务 | 状态 | 说明 |
|------|------|------|
| Redis | ✅ 运行中 | Docker 容器 `xihong_erp_redis` 正常运行 |
| 后端服务 | ❌ 未运行 | 需要启动后端服务 (`http://localhost:8001`) |
| Celery Worker | ❓ 未知 | 需要检查是否运行 |

### 测试脚本

已创建测试脚本：
- `scripts/test_celery_task_status.py` - 任务状态管理 API 测试脚本

---

## 🧪 测试执行

### 测试 1: 服务健康检查

**测试时间**: 2026-01-03  
**测试结果**: ❌ 失败

**错误信息**:
```
HTTPConnectionPool(host='localhost', port=8001): Read timed out. (read timeout=5)
```

**原因分析**:
- 后端服务未运行或无法连接
- 需要先启动后端服务

**解决方案**:
```bash
# 启动后端服务
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

---

## 📝 测试步骤（待执行）

### 步骤 1: 启动服务

1. **启动后端服务**:
```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

2. **启动 Celery Worker** (新终端窗口):
```bash
# Windows
python -m celery -A backend.celery_app worker --loglevel=info --queues=data_sync,scheduled --pool=solo --concurrency=4

# Linux/Mac
celery -A backend.celery_app worker --loglevel=info --queues=data_sync,scheduled --concurrency=4
```

3. **验证服务状态**:
```bash
# 检查后端服务
curl http://localhost:8001/health

# 检查 Redis
docker exec xihong_erp_redis redis-cli ping
```

### 步骤 2: 执行测试

运行测试脚本：
```bash
python scripts/test_celery_task_status.py
```

### 步骤 3: 测试任务恢复机制

1. **提交一个任务**:
```bash
curl -X POST "http://localhost:8001/api/data-sync/sync-single-file" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "file_id": 1,
    "priority": 5
  }'
```

2. **记录返回的 `celery_task_id`**

3. **查询任务状态**:
```bash
curl "http://localhost:8001/api/data-sync/task-status/<celery_task_id>" \
  -H "Authorization: Bearer <token>"
```

4. **重启 Celery Worker** (停止并重新启动)

5. **再次查询任务状态**，验证任务是否恢复

### 步骤 4: 测试任务取消

1. **提交一个任务**（记录 `celery_task_id`）

2. **立即取消任务**:
```bash
curl -X DELETE "http://localhost:8001/api/data-sync/cancel-task/<celery_task_id>" \
  -H "Authorization: Bearer <token>"
```

3. **验证任务状态**，应该为 `REVOKED`

### 步骤 5: 性能测试

1. **测试任务提交速度**:
```bash
# 使用测试脚本或手动测试
time curl -X POST "http://localhost:8001/api/data-sync/sync-single-file" ...
```

2. **测试并发任务处理**:
```bash
# 同时提交 10 个任务
for i in {1..10}; do
  curl -X POST "http://localhost:8001/api/data-sync/sync-single-file" ... &
done
wait
```

---

## 📊 测试结果记录

### 功能测试

| 测试项 | 状态 | 备注 |
|--------|------|------|
| 服务健康检查 | ❌ 未通过 | 后端服务未运行 |
| 任务提交 | ⬜ 待测试 | |
| 任务状态查询 | ⬜ 待测试 | |
| 任务取消 | ⬜ 待测试 | |
| 任务恢复机制 | ⬜ 待测试 | |

### 性能测试

| 测试项 | 状态 | 结果 |
|--------|------|------|
| 任务提交速度 | ⬜ 待测试 | 目标: <100ms |
| 任务执行速度 | ⬜ 待测试 | 目标: 与之前相同 |
| 并发任务处理 | ⬜ 待测试 | 目标: 10 个并发任务 |
| Redis 内存使用 | ⬜ 待测试 | 目标: <1GB |

### 压力测试

| 测试项 | 状态 | 结果 |
|--------|------|------|
| 100 个并发任务 | ⬜ 待测试 | |
| 服务器重启恢复 | ⬜ 待测试 | |
| Redis 降级处理 | ⬜ 待测试 | |

---

## 🔧 故障排查

### 问题 1: 后端服务无法连接

**症状**: `HTTPConnectionPool(host='localhost', port=8001): Read timed out`

**解决方案**:
1. 检查后端服务是否运行: `netstat -an | findstr 8001`
2. 启动后端服务: `uvicorn main:app --reload --host 0.0.0.0 --port 8001`
3. 检查防火墙设置

### 问题 2: Celery Worker 无法连接 Redis

**症状**: `Error: No connection could be made because the target machine actively refused it`

**解决方案**:
1. 检查 Redis 是否运行: `docker ps | grep redis`
2. 检查 Redis 连接配置: `CELERY_BROKER_URL` 环境变量
3. 启动 Redis: `docker-compose up -d redis`

### 问题 3: 任务无法提交

**症状**: 返回错误或降级到 `asyncio.create_task()`

**解决方案**:
1. 检查 Celery Worker 是否运行
2. 检查 Redis 连接
3. 查看后端日志: `logs/backend/`

---

## 📝 测试脚本使用说明

### 基本使用

```bash
# 运行测试脚本
python scripts/test_celery_task_status.py
```

### 配置认证 Token

如果需要认证，修改脚本中的 `AUTH_TOKEN` 变量：

```python
AUTH_TOKEN = "your_token_here"
```

### 修改测试文件ID

修改脚本中的 `TEST_FILE_ID` 变量：

```python
TEST_FILE_ID = 1  # 改为实际的文件ID
```

---

## ✅ 下一步

1. **启动服务**: 启动后端服务和 Celery Worker
2. **执行测试**: 运行测试脚本进行基本功能测试
3. **验证恢复机制**: 测试任务恢复功能
4. **性能测试**: 执行性能测试和压力测试
5. **更新报告**: 根据测试结果更新本报告

---

**最后更新**: 2026-01-03  
**状态**: ⚠️ 待执行（需要先启动服务）

