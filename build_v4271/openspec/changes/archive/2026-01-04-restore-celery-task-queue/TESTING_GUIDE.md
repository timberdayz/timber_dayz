# Celery 任务队列测试指南

**创建日期**: 2026-01-03  
**状态**: 测试指南  
**用途**: 验证 Celery 任务队列的各项功能

---

## 📋 测试前准备

### 1. 环境要求

- ✅ Celery Worker 正在运行
- ✅ Redis 服务正常运行
- ✅ 后端服务正常运行
- ✅ 数据库连接正常

### 2. 启动服务

```bash
# 启动 Celery Worker（Windows）
python -m celery -A backend.celery_app worker --loglevel=info --queues=data_sync,scheduled --pool=solo --concurrency=4

# 启动 Celery Worker（Linux/Mac）
celery -A backend.celery_app worker --loglevel=info --queues=data_sync,scheduled --concurrency=4

# 或使用 Docker Compose
docker-compose -f docker-compose.prod.yml up -d celery-worker
```

---

## 🧪 测试 1: 任务恢复机制验证

### 测试目标

验证 Celery Worker 重启后，未完成的任务能够自动恢复。

### 测试步骤

#### 步骤 1: 提交一个长时间运行的任务

```bash
# 使用 API 提交一个批量同步任务（选择大量文件）
curl -X POST "http://localhost:8001/api/data-sync/sync-batch" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "platform": "shopee",
    "limit": 100,
    "priority": 5
  }'
```

**记录返回的 `celery_task_id`**。

#### 步骤 2: 查询任务状态

```bash
# 查询任务状态
curl "http://localhost:8001/api/data-sync/task-status/<celery_task_id>" \
  -H "Authorization: Bearer <token>"
```

确认任务状态为 `STARTED` 或 `PENDING`。

#### 步骤 3: 重启 Celery Worker

```bash
# 停止 Celery Worker
# Windows: Ctrl+C
# Linux/Mac: kill <pid>
# Docker: docker-compose -f docker-compose.prod.yml restart celery-worker

# 等待 5 秒后重新启动
# 重新运行启动命令
```

#### 步骤 4: 验证任务恢复

```bash
# 等待 10 秒后，再次查询任务状态
curl "http://localhost:8001/api/data-sync/task-status/<celery_task_id>" \
  -H "Authorization: Bearer <token>"
```

**预期结果**：
- ✅ 任务状态应该从 `PENDING` 或 `STARTED` 继续执行
- ✅ 任务最终应该完成（`SUCCESS`）或失败（`FAILURE`）
- ✅ 不应该出现任务丢失的情况

### 验证清单

- [ ] 任务在 Worker 重启后能够继续执行
- [ ] 任务状态正确更新
- [ ] 任务结果正确保存
- [ ] 没有任务丢失

---

## ⚡ 测试 2: 性能测试

### 测试目标

验证任务提交和执行性能，确保满足性能要求。

### 测试 2.1: 任务提交速度

#### 测试步骤

```bash
# 使用脚本测试任务提交速度
python scripts/test_celery_task_submit_performance.py
```

**预期结果**：
- ✅ 任务提交时间 < 100ms（P95）
- ✅ 任务提交成功率 = 100%

#### 手动测试

```bash
# 记录开始时间
start_time=$(date +%s%N)

# 提交任务
curl -X POST "http://localhost:8001/api/data-sync/sync-single-file" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "file_id": 1,
    "priority": 5
  }'

# 记录结束时间
end_time=$(date +%s%N)

# 计算耗时（毫秒）
duration=$((($end_time - $start_time) / 1000000))
echo "任务提交耗时: ${duration}ms"
```

### 测试 2.2: 任务执行速度

#### 测试步骤

```bash
# 提交一个单文件同步任务
curl -X POST "http://localhost:8001/api/data-sync/sync-single-file" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "file_id": 1,
    "priority": 5
  }'

# 记录 celery_task_id，然后轮询查询任务状态
# 直到任务完成（ready=True）
```

**预期结果**：
- ✅ 任务执行速度应该与之前使用 `asyncio.create_task()` 时相同或更快
- ✅ 任务执行时间应该 < 30 分钟（超时限制）

### 测试 2.3: 并发任务处理能力

#### 测试步骤

```bash
# 同时提交 10 个任务
for i in {1..10}; do
  curl -X POST "http://localhost:8001/api/data-sync/sync-single-file" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer <token>" \
    -d "{
      \"file_id\": $i,
      \"priority\": 5
    }" &
done
wait

# 查询所有任务的状态
# 验证所有任务都能正常执行
```

**预期结果**：
- ✅ 所有任务都能正常提交
- ✅ 所有任务都能正常执行
- ✅ 任务执行时间合理（不会因为并发而显著增加）

### 测试 2.4: Redis 内存使用

#### 测试步骤

```bash
# 查看 Redis 内存使用
docker-compose -f docker-compose.prod.yml exec redis redis-cli INFO memory

# 提交大量任务后，再次查看内存使用
# 验证内存使用是否合理
```

**预期结果**：
- ✅ Redis 内存使用应该 < 1GB（1000 个任务）
- ✅ 任务结果过期后，内存应该自动释放

---

## 🔥 测试 3: 压力测试

### 测试目标

验证系统在高负载下的稳定性和性能。

### 测试 3.1: 100 个并发任务

#### 测试步骤

```bash
# 创建测试脚本
cat > test_100_concurrent_tasks.sh << 'EOF'
#!/bin/bash
for i in {1..100}; do
  curl -X POST "http://localhost:8001/api/data-sync/sync-single-file" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer <token>" \
    -d "{
      \"file_id\": $i,
      \"priority\": 5
    }" &
done
wait
EOF

chmod +x test_100_concurrent_tasks.sh
./test_100_concurrent_tasks.sh
```

**预期结果**：
- ✅ 所有任务都能正常提交（100% 成功率）
- ✅ 系统不会崩溃或出现严重性能问题
- ✅ 任务能够正常执行完成

### 测试 3.2: 服务器重启后任务恢复

#### 测试步骤

1. **提交多个任务**：
```bash
# 提交 10 个任务
for i in {1..10}; do
  curl -X POST "http://localhost:8001/api/data-sync/sync-single-file" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer <token>" \
    -d "{
      \"file_id\": $i,
      \"priority\": 5
    }"
done
```

2. **记录所有任务的 `celery_task_id`**

3. **重启服务器**：
```bash
# 重启 Docker 服务
docker-compose -f docker-compose.prod.yml restart

# 或重启 Celery Worker
docker-compose -f docker-compose.prod.yml restart celery-worker
```

4. **验证任务恢复**：
```bash
# 等待 30 秒后，查询所有任务状态
for task_id in <task_id_list>; do
  curl "http://localhost:8001/api/data-sync/task-status/$task_id" \
    -H "Authorization: Bearer <token>"
done
```

**预期结果**：
- ✅ 所有未完成的任务都应该能够恢复
- ✅ 任务状态应该正确更新
- ✅ 不应该出现任务丢失

### 测试 3.3: Redis 连接失败时的降级处理

#### 测试步骤

1. **提交一个任务**：
```bash
curl -X POST "http://localhost:8001/api/data-sync/sync-single-file" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "file_id": 1,
    "priority": 5
  }'
```

2. **停止 Redis 服务**：
```bash
docker-compose -f docker-compose.prod.yml stop redis
```

3. **提交另一个任务**：
```bash
curl -X POST "http://localhost:8001/api/data-sync/sync-single-file" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "file_id": 2,
    "priority": 5
  }'
```

**预期结果**：
- ✅ 任务应该降级到 `asyncio.create_task()` 模式
- ✅ 任务应该能够正常执行
- ✅ 应该记录降级日志

4. **恢复 Redis 服务**：
```bash
docker-compose -f docker-compose.prod.yml start redis
```

5. **验证后续任务使用 Celery**：
```bash
# 提交新任务，验证是否使用 Celery
curl -X POST "http://localhost:8001/api/data-sync/sync-single-file" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "file_id": 3,
    "priority": 5
  }'
```

**预期结果**：
- ✅ 任务应该使用 Celery 执行（返回 `celery_task_id`）
- ✅ 不应该再降级到 `asyncio.create_task()`

---

## 📊 测试结果记录

### 测试环境信息

- **测试日期**: _______________
- **测试人员**: _______________
- **Celery Worker 版本**: _______________
- **Redis 版本**: _______________
- **并发数**: _______________

### 测试结果

| 测试项 | 状态 | 备注 |
|--------|------|------|
| 任务恢复机制 | ⬜ 通过 / ⬜ 失败 | |
| 任务提交速度 | ⬜ 通过 / ⬜ 失败 | 平均耗时: _____ ms |
| 任务执行速度 | ⬜ 通过 / ⬜ 失败 | 平均耗时: _____ s |
| 并发任务处理 | ⬜ 通过 / ⬜ 失败 | 并发数: _____ |
| Redis 内存使用 | ⬜ 通过 / ⬜ 失败 | 内存使用: _____ MB |
| 100 个并发任务 | ⬜ 通过 / ⬜ 失败 | |
| 服务器重启恢复 | ⬜ 通过 / ⬜ 失败 | |
| Redis 降级处理 | ⬜ 通过 / ⬜ 失败 | |

### 问题记录

1. **问题描述**: _______________
   - **复现步骤**: _______________
   - **预期结果**: _______________
   - **实际结果**: _______________
   - **解决方案**: _______________

---

## 🔧 故障排查

### 问题 1: 任务无法提交

**可能原因**：
- Celery Worker 未运行
- Redis 连接失败
- 任务参数错误

**排查步骤**：
```bash
# 检查 Celery Worker 状态
docker-compose -f docker-compose.prod.yml ps celery-worker

# 检查 Redis 连接
docker-compose -f docker-compose.prod.yml exec redis redis-cli ping

# 查看后端日志
docker-compose -f docker-compose.prod.yml logs backend | tail -50
```

### 问题 2: 任务执行失败

**可能原因**：
- 数据库连接失败
- 文件不存在
- 任务超时

**排查步骤**：
```bash
# 查看任务错误信息
curl "http://localhost:8001/api/data-sync/task-status/<celery_task_id>" \
  -H "Authorization: Bearer <token>"

# 查看 Celery Worker 日志
docker-compose -f docker-compose.prod.yml logs celery-worker | grep -i error
```

### 问题 3: 任务无法恢复

**可能原因**：
- Redis 持久化未启用
- 任务已确认（`task_acks_late=False`）
- Redis 数据丢失

**排查步骤**：
```bash
# 检查 Redis 持久化配置
docker-compose -f docker-compose.prod.yml exec redis redis-cli INFO persistence

# 检查 Celery 配置
docker-compose -f docker-compose.prod.yml exec celery-worker celery -A backend.celery_app inspect active
```

---

## 📝 测试脚本

### 创建测试脚本

可以创建以下测试脚本来自动化测试：

1. `scripts/test_task_recovery.py` - 任务恢复测试
2. `scripts/test_performance.py` - 性能测试
3. `scripts/test_stress.py` - 压力测试

这些脚本可以集成到 CI/CD 流程中，定期执行测试。

---

**最后更新**: 2026-01-03  
**维护**: AI Agent Team  
**状态**: ✅ 测试指南已创建

