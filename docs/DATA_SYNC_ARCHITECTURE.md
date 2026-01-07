# 数据同步架构文档

**版本**: v4.12.3  
**最后更新**: 2025-01-31  
**状态**: ✅ 生产就绪

---

## 📋 架构概述

数据同步功能采用**FastAPI BackgroundTasks**实现异步处理，无需额外的Celery Worker。

### 核心组件

1. **API路由** (`backend/routers/data_sync.py`)
   - 接收同步请求
   - 创建进度任务
   - 提交后台任务

2. **后台处理函数** (`process_batch_sync_background`)
   - 并发控制（最多10个并发）
   - 数据质量Gate检查
   - 进度跟踪更新

3. **进度跟踪器** (`backend/services/sync_progress_tracker.py`)
   - 数据库存储进度
   - 支持任务查询和历史记录
   - **事务一致性保证**：查询前自动回滚失败事务，支持重试机制（最多3次）
   - **错误处理**：完善的错误处理和日志记录，不影响后台任务执行

---

## 🔄 数据流程

```
用户请求
  ↓
POST /api/data-sync/batch
  ↓
创建进度任务（数据库）
  ↓
提交BackgroundTask（立即返回task_id）
  ↓
后台异步处理
  ├─ 并发控制（Semaphore）
  ├─ 文件同步（DataSyncService）
  ├─ 进度更新（SyncProgressTracker）
  └─ 质量检查（CClassDataValidator）
  ↓
完成任务（更新状态）
  ↓
前端轮询进度
```

---

## 🎯 关键特性

### 1. 异步处理
- ✅ 使用FastAPI BackgroundTasks（内置）
- ✅ API立即返回，不阻塞
- ✅ 后台自动处理

### 2. 并发控制
- ✅ 最多10个并发文件处理
- ✅ 使用asyncio.Semaphore限制
- ✅ 避免资源耗尽

### 3. 进度跟踪
- ✅ 数据库持久化存储
- ✅ 实时更新进度
- ✅ 支持任务查询和历史记录
- ✅ **事务一致性保证**：查询前自动回滚失败事务，避免`InFailedSqlTransaction`错误
- ✅ **重试机制**：自动重试查询（最多3次），等待时间递增（0.1秒、0.2秒、0.3秒）
- ✅ **备用方案**：查询失败时，前端可从任务列表获取进度信息

### 4. 数据质量Gate
- ✅ 批量同步完成后自动质量检查
- ✅ 计算平均质量评分
- ✅ 识别缺失字段

### 5. 错误处理和状态同步（v4.12.3新增）
- ✅ **数据库事务管理**：每次查询前自动回滚失败事务，确保使用干净的事务
- ✅ **重试机制**：遇到`InFailedSqlTransaction`错误时自动重试（最多3次）
- ✅ **前端错误处理**：完善的null检查，区分"查询失败"和"任务失败"
- ✅ **备用查询方案**：进度查询失败时，前端可从任务列表获取进度信息
- ✅ **数据治理概览自动刷新**：同步完成后自动刷新数据治理概览（异步执行，不阻塞用户操作）
- ✅ **字段映射关系**：后端返回`valid_rows/quarantined_rows/error_rows`，前端使用`succeeded/quarantined/failed`（API客户端自动映射）

---

## 📊 API端点

### 1. 批量同步
```http
POST /api/data-sync/batch
Content-Type: application/json

{
  "platform": "shopee",
  "domains": ["orders"],
  "limit": 100,
  "only_with_template": true,
  "allow_quarantine": true
}
```

**响应**:
```json
{
  "success": true,
  "task_id": "batch_xxxxx",
  "message": "批量同步任务已提交，正在处理100个文件",
  "total_files": 100,
  "processed_files": 0
}
```

### 2. 查询进度
```http
GET /api/data-sync/progress/{task_id}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "task_id": "batch_xxxxx",
    "status": "processing",
    "total_files": 100,
    "processed_files": 50,
    "file_progress": 50.0,
    "current_file": "shopee_orders_20250118.xlsx",
    "valid_rows": 1500,
    "quarantined_rows": 5,
    "error_rows": 0
  }
}
```

### 3. 任务列表
```http
GET /api/data-sync/tasks?status=completed&limit=10
```

---

## 🔧 配置说明

### 并发控制
默认最多10个并发文件处理，可在`process_batch_sync_background`函数中调整：
```python
max_concurrent=10  # 可调整
```

### 进度跟踪
进度存储在`sync_progress_tasks`表中，包含：
- 任务ID、类型、状态
- 文件进度、行数统计
- 当前文件、错误信息
- 任务详情（质量检查结果）

---

## 🚀 部署说明

### 数据同步（无需额外配置）
```bash
# 只需启动FastAPI服务
python run.py --backend-only
```

### 定时任务（需要Celery）
```bash
# Worker（处理定时任务）
python -m celery -A backend.celery_app worker --queues=scheduled,data_processing

# Beat（定时调度）
python -m celery -A backend.celery_app beat
```

---

## 🔍 错误处理和状态同步机制（v4.12.3）

### 数据库事务一致性保证

**问题**：进度查询时遇到`InFailedSqlTransaction`错误，导致查询失败。

**解决方案**：
1. **查询前事务回滚**：每次查询前先回滚任何失败的事务，确保使用干净的事务
2. **自动重试机制**：遇到事务错误时自动重试（最多3次），等待时间递增（0.1秒、0.2秒、0.3秒）
3. **API层面事务管理**：API异常时确保回滚事务，避免影响后续查询

**实现位置**：
- `backend/services/sync_progress_tracker.py`：`get_task()`方法
- `backend/routers/data_sync.py`：`get_sync_progress()`端点

### 前端错误处理

**问题**：访问null对象的属性导致前端崩溃，无法区分"查询失败"和"任务失败"。

**解决方案**：
1. **完善的null检查**：所有API响应都进行null检查，避免访问null的属性
2. **错误消息区分**：区分"查询失败"（HTTP 500/数据库错误）和"任务失败"（HTTP 404/任务不存在）
3. **备用查询方案**：查询失败时，前端从任务列表获取进度信息
4. **连续失败处理**：连续10次查询失败且找不到任务时，显示"无法获取进度，请刷新页面查看最新状态"

**实现位置**：
- `frontend/src/views/FieldMappingEnhanced.vue`：`pollSyncProgress()`方法
- `frontend/src/api/index.js`：`getAutoIngestProgress()`方法

### 数据治理概览自动刷新

**问题**：同步完成后，数据治理概览不自动更新。

**解决方案**：
1. **自动刷新**：同步完成（status为completed或failed）时自动调用`refreshGovernanceStats()`
2. **异步执行**：刷新是异步的，不阻塞用户操作
3. **错误处理**：刷新失败时记录错误日志，但不影响同步结果
4. **响应格式解析**：响应拦截器已提取data字段，前端直接使用overview（不检查overview.success或overview.data）

**实现位置**：
- `frontend/src/views/FieldMappingEnhanced.vue`：`pollSyncProgress()`方法中的完成处理

### 字段映射关系

**后端返回字段**：
- `valid_rows`：有效行数（成功入库）
- `quarantined_rows`：隔离行数（数据质量问题）
- `error_rows`：错误行数（处理失败）

**前端使用字段**：
- `succeeded`：成功行数（映射自`valid_rows`）
- `quarantined`：隔离行数（映射自`quarantined_rows`）
- `failed`：失败行数（映射自`error_rows`）

**映射位置**：`frontend/src/api/index.js`的`getAutoIngestProgress()`方法自动完成字段映射。

---

## 📝 相关文档

- [简化方案报告](DATA_SYNC_SIMPLIFICATION_REPORT.md)
- [设置指南](DATA_SYNC_SETUP_GUIDE.md)
- [合规性评估](DATA_SYNC_ERP_COMPLIANCE_ASSESSMENT.md)

---

**最后更新**: 2025-01-31  
**维护者**: AI Agent

---

## 📋 变更历史

### v4.12.3 (2025-01-31)
- ✅ 添加数据库事务一致性保证（查询前回滚、重试机制）
- ✅ 改进前端错误处理（null检查、错误消息区分、备用方案）
- ✅ 实现数据治理概览自动刷新（异步执行、错误处理）
- ✅ 明确字段映射关系（后端字段→前端字段）

### v4.12.2 (2025-11-18)
- ✅ 数据同步改用FastAPI BackgroundTasks（简化）
- ✅ 移除Celery依赖（数据同步）
