# Change: 恢复 Celery 任务队列并优化生产环境架构

> **状态**: ✅ Phase 1-7 全部完成 (2026-01-04)  
> **说明**: Phase 6 监控和告警的配置工作已完成，待实际部署验证

## Why

当前系统在 **50-100 人生产环境**下存在严重的架构问题：

### 1. 任务持久化不足（高严重性）

- **问题**：数据同步任务使用 `asyncio.create_task()` 在内存中执行，服务器重启后任务丢失
- **影响**：用户需要重新提交任务，进度虽然可以恢复，但任务不会自动重新执行
- **场景**：服务器维护、崩溃、部署更新时，所有正在执行的任务都会丢失

### 2. 资源隔离不足（高严重性）

- **问题**：所有任务在同一个 FastAPI 进程中执行，一个用户的大量任务可能影响其他用户
- **影响**：用户 A 提交 100 个文件同步任务时，可能阻塞其他用户的 API 请求
- **场景**：50-100 人同时使用时，资源竞争导致系统响应变慢

### 3. 无法水平扩展（中严重性）

- **问题**：无法通过增加 worker 来扩展处理能力
- **影响**：高峰期（50-100 人同时使用）时，所有任务在同一个进程中执行，可能造成资源竞争
- **场景**：系统负载高时，无法通过增加 worker 来提升处理能力

### 4. 缺少任务队列功能（中严重性）

- **问题**：无法实现任务优先级、限流、重试等高级功能
- **影响**：无法根据业务需求调整任务执行顺序，无法限制单个用户的任务数量
- **场景**：紧急任务无法优先执行，恶意用户可能提交大量任务导致系统瘫痪

### 历史背景

**v4.12.2 简化决策**：

- 将数据同步任务从 Celery 迁移到 FastAPI BackgroundTasks
- 原因：减少复杂度，无需额外的 Celery Worker
- **问题**：这个决策适合小规模使用，但不适合 50-100 人的生产环境

**当前状态**：

- Celery 配置仍然存在（`backend/celery_app.py`），但仅用于定时任务
- Redis 已部署（用于 Celery broker 和 result backend）
- 数据同步任务使用 `asyncio.create_task()` + `asyncio.Semaphore(10)` 控制并发

## What Changes

### Phase 1: 恢复 Celery 任务队列（数据同步）- P0 ✅

#### 1.1 创建数据同步任务模块

- [x] 创建 `backend/tasks/data_sync_tasks.py`
- [x] 将 `process_single_sync_background` 迁移为 Celery 任务
- [x] 将 `process_batch_sync_background` 迁移为 Celery 任务
- [x] 保持现有功能（并发控制、进度跟踪、质量检查）

#### 1.2 更新 Celery 配置

- [x] 更新 `backend/celery_app.py`，添加 `data_sync` 队列
- [x] 配置任务路由和优先级
- [x] 配置任务重试机制

#### 1.3 更新 API 路由

- [x] 修改 `backend/routers/data_sync.py`，使用 Celery 任务替代 `asyncio.create_task()`
- [x] 保持 API 响应格式不变（立即返回 `task_id`）
- [x] 保持进度跟踪机制不变（使用 `SyncProgressTracker`）
- [x] 实现降级机制（Celery 不可用时回退到 `asyncio.create_task()`）

#### 1.4 任务持久化和恢复

- [x] 配置 Celery 使用 Redis 持久化任务（AOF + RDB）
- [x] 配置 `task_acks_late` 和 `task_reject_on_worker_lost`
- [x] 验证 Redis 8.2.3 满足版本要求

### Phase 2: 添加 Nginx 反向代理和限流 - P1 ✅

#### 2.1 Nginx 配置

- [x] 更新 `nginx/nginx.prod.conf` 配置文件
- [x] 配置反向代理到 FastAPI（`http://backend:8000`）
- [x] 配置静态资源缓存
- [x] ⭐ **新增**：添加限流配置（按 IP 限流）

#### 2.2 API 限流

- [x] 配置 Nginx 限流（按 IP，不同 API 路径不同限流规则）
- [x] 配置 FastAPI 限流（使用 `slowapi`，已为数据同步 API 添加限流装饰器）
- [ ] 实现用户级别的任务数量限制（Phase 4，需要先实现用户认证）

### Phase 3: 添加 Redis 缓存层 - P2 ✅

#### 3.1 缓存策略

- [x] 缓存频繁查询的数据（账号列表、组件版本列表）
- [x] 实现缓存失效机制（TTL 过期）
- [x] 添加缓存监控（统计命中率）

#### 3.2 缓存服务

- [x] 创建 `backend/services/cache_service.py`
- [x] 实现缓存装饰器（`@cache_result`）
- [x] 更新相关 API 使用缓存（账号列表、组件版本列表）

### Phase 4: 任务优先级和用户隔离 - P3 ✅

#### 4.1 任务优先级 ✅

- [x] 实现任务优先级队列（1-10，10 最高，默认 5）
- [x] 配置 Celery 任务优先级路由（已在 Phase 1 中配置 `task_default_priority=5`）
- [x] 更新 API 支持优先级参数（所有数据同步 API 已支持 `priority` 参数）

#### 4.2 用户隔离 ✅

- [x] **前提条件**：在 API 路由中添加用户认证（`get_current_user` 依赖）
- [x] 实现每个用户最多同时运行 N 个任务（默认 10 个，使用 Redis 跟踪）
- [x] 添加用户任务队列管理（`UserTaskQuotaService`）
- [x] 实现任务配额机制（任务提交前检查，任务完成/失败时减少计数）
- [x] **注意**：当前数据同步 API 没有用户认证，此功能需要先实现认证机制

### Phase 5: 限流系统改进 - P1 ✅

> **状态**: ✅ 已完成（2026-01-04）  
> **前置条件**: Phase 1-4 已完成，并发任务测试发现限流问题  
> **优先级**: P1 - 改进限流系统，支持用户级限流  
> **详细报告**: [RATE_LIMIT_IMPROVEMENTS.md](RATE_LIMIT_IMPROVEMENTS.md)

#### 5.1 用户级限流 ✅

- [x] 从 IP 限流改为用户 ID 限流（`get_rate_limit_key()` 函数）
- [x] 未认证用户降级到 IP 限流
- [x] 限流键格式: `user:{user_id}` 或 `ip:{ip_address}`

#### 5.2 限流响应头 ✅

- [x] 添加标准 HTTP 限流响应头：
  - `X-RateLimit-Limit`: 限流值
  - `X-RateLimit-Remaining`: 剩余请求数
  - `X-RateLimit-Reset`: 重置时间戳
  - `Retry-After`: 重试等待时间
- [x] 增强错误响应信息（`rate_limit_type`, `rate_limit_key`）

#### 5.3 分级限流 ✅

- [x] 实现基于用户角色的分级限流配置（`RATE_LIMIT_TIERS`）
- [x] admin: 200/分钟（默认）、100/分钟（数据同步）、20/分钟（认证）
- [x] premium/normal/anonymous: 不同配额配置
- [x] 实现用户等级获取函数（`get_user_rate_limit_tier()`）

#### 5.4 限流监控 ✅

- [x] 创建限流统计服务（`backend/services/rate_limit_stats.py`）
- [x] 创建限流管理 API（`backend/routers/rate_limit.py`）
- [x] API 端点：
  - `GET /api/rate-limit/config` - 获取限流配置（Admin）
  - `GET /api/rate-limit/stats` - 获取限流统计（Admin）
  - `GET /api/rate-limit/events` - 获取限流事件（Admin）
  - `GET /api/rate-limit/anomalies` - 检查异常流量（Admin）
  - `GET /api/rate-limit/my-info` - 获取当前用户限流信息（登录）
- [x] 支持限流事件记录、统计查询、异常检测

#### 5.5 测试验证 ✅

- [x] 创建测试脚本（`scripts/test_rate_limit_improvements.py`）
- [x] 所有 7 个测试全部通过
- [x] 验证用户级限流、响应头、配置 API、统计 API 等功能

### Phase 6: 监控和告警 - P1 ✅

> **状态**: ✅ 配置工作已完成，待实际部署验证 (2026-01-04)  
> **前置条件**: Phase 1-5 已完成  
> **优先级**: P1 - 生产环境必需  
> **实施方案**: 方案 A - 使用 Celery Exporter（推荐）  
> **详细文档**: [MONITORING_AND_ALERTING_IMPLEMENTATION.md](MONITORING_AND_ALERTING_IMPLEMENTATION.md)  
> **实施状态**: [PHASE6_IMPLEMENTATION_STATUS.md](PHASE6_IMPLEMENTATION_STATUS.md)  
> **漏洞修复**: [VULNERABILITY_FIXES.md](VULNERABILITY_FIXES.md)

#### 6.1 任务监控 ✅

- [x] 部署 Celery Exporter（独立服务）

  - [x] 在 `docker-compose.prod.yml` 中添加 celery-exporter 服务
  - [x] 配置 Celery Broker 连接（Redis，包含密码）
  - [x] 配置监听端口（9808）
  - [x] 配置健康检查
  - [ ] 验证 `/metrics` 端点可访问（待实际部署验证）

- [x] 配置 Prometheus 抓取

  - [x] 更新 `monitoring/prometheus.yml`，添加 Celery Exporter 抓取配置
  - [x] 配置抓取间隔（15 秒）和超时（10 秒）
  - [ ] 验证 Prometheus 能正常抓取指标（待实际部署验证）

- [x] 监控指标收集
  - [x] 监控任务执行时间（通过 Celery Exporter 自动收集）
  - [x] 监控任务失败率（通过 Celery Exporter 自动收集）
  - [x] 监控任务队列长度（通过 Celery Exporter 自动收集）
  - [x] 监控 Worker 状态（通过 Celery Exporter 自动收集）

#### 6.2 告警规则 ✅

- [x] 设计告警规则

  - [x] 任务失败率告警（阈值：>10%，持续 5 分钟） → **HighCeleryTaskFailureRate**
  - [x] 任务队列长度告警（阈值：>100，持续 5 分钟） → **HighCeleryQueueLength**
  - [x] 任务执行时间告警（阈值：P95 > 30 分钟，持续 10 分钟） → **HighCeleryTaskExecutionTime**
  - [x] Worker 离线告警（持续 2 分钟） → **CeleryWorkerDown**
  - [x] Redis 连接失败告警（立即告警） → **CeleryRedisConnectionFailed**

- [x] 添加告警规则

  - [x] 更新 `monitoring/alert_rules.yml`，添加 `celery_alerts` 规则组
  - [x] 配置告警标签（severity: warning/critical, component: celery）
  - [x] 配置告警描述和摘要

- [x] 配置 AlertManager
  - [x] 创建 `monitoring/alertmanager.yml` 配置文件
  - [x] 在 `docker/docker-compose.monitoring.yml` 中添加 AlertManager 服务
  - [x] 配置通知渠道（邮件、Webhook）
  - [x] 配置路由规则（按 severity 和 component 路由）
  - [x] 配置告警去重和抑制规则

#### 6.3 可视化 ✅

- [x] 部署 Grafana

  - [x] 在 `docker/docker-compose.monitoring.yml` 中配置 Grafana 服务
  - [x] 配置 Prometheus 数据源 → **monitoring/grafana/provisioning/datasources/prometheus.yml**
  - [x] 配置用户认证（使用环境变量）

- [x] 创建监控仪表板
  - [x] 创建 Celery 任务监控面板 → **monitoring/grafana/dashboards/celery-monitoring.json**
  - [x] 6 个监控面板：Tasks Rate、Failure Rate、Queue Length、Tasks by State、Exporter Status、Duration P95

#### 6.4 测试验证 ✅

- [x] 创建测试脚本

  - [x] `scripts/test_monitoring_setup.py` → **自动化测试脚本**

- [ ] 功能测试（待实际部署验证）

  - [ ] 测试指标收集是否正常
  - [ ] 测试告警触发是否正常
  - [ ] 测试通知发送是否正常

- [ ] 性能测试（待生产环境验证）
  - [ ] 验证监控对系统性能影响
  - [ ] 验证 Prometheus 存储性能

### Phase 7: 部署配置优化 - P2 ✅

> **状态**: ✅ 已完成（2026-01-04，包含健康检查、队列路由和模块包含优化）  
> **优先级**: P2 - 改进建议，提升部署可靠性（包含 1 个 P0 修复）  
> **说明**: 基于最终漏洞审查发现的改进项

#### 7.1 Celery Worker 健康检查 ✅

- [x] 添加 Celery Worker 健康检查配置
  - [x] 在 `docker-compose.prod.yml` 中添加 `healthcheck` 配置
  - [x] ⭐ **修复**：使用进程检查方式（`ps aux | grep '[c]elery.*worker'`），比 `inspect ping` 更可靠
  - [x] 配置检查间隔（30 秒）、超时（10 秒）、重试次数（3 次）
  - [x] 配置启动等待时间（40 秒）

**配置说明**：

```yaml
healthcheck:
  # 使用进程检查方式（更可靠），检查 celery worker 进程是否存在
  test: ["CMD-SHELL", "ps aux | grep '[c]elery.*worker' || exit 1"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

**优势**：

- ✅ 确保 Worker 正常运行后才认为服务就绪
- ✅ 支持 `depends_on` 的 `condition: service_healthy` 依赖
- ✅ 自动检测 Worker 崩溃并触发重启
- ✅ 使用进程检查方式，比 `inspect ping` 更可靠（不依赖 worker 控制接口）

#### 7.2 队列配置说明完善 ✅

- [x] 明确队列配置说明
  - [x] 在 `docker-compose.prod.yml` 中添加队列说明注释
  - [x] 说明每个队列的用途：
    - `data_sync`: 数据同步任务（主要业务任务）
    - `scheduled`: 定时任务（由 Celery Beat 调度）
    - `data_processing`: 数据处理任务（Excel 处理、图片提取等）
  - [x] 更新启动命令，包含所有需要的队列
  - [x] ⭐ **修复**：在 `backend/celery_app.py` 中添加 `extract_product_images` 任务的路由规则
  - [x] ⭐ **修复**：更新 `backend/celery_app.py` 中的启动说明，包含 `data_processing` 队列
  - [x] ⭐ **修复（P0）**：在 `backend/celery_app.py` 的 `include` 列表中添加 `backend.tasks.image_extraction` 模块
  - [x] ⭐ **修复（P0）**：在 `backend/celery_app.py` 的 `include` 列表中添加 `backend.tasks.image_extraction` 模块

**队列配置**：

```bash
--queues=data_sync,scheduled,data_processing
```

**说明**：

- `data_sync`: 数据同步任务，核心业务功能
- `scheduled`: 定时任务，由 Celery Beat 自动调度
- `data_processing`: 数据处理任务，包括：
  - Excel 文件处理（`backend.tasks.data_processing.*`）
  - 产品图片提取（`extract_product_images`，已配置路由规则）

**任务路由配置**（`backend/celery_app.py`）：

```python
task_routes={
    'backend.tasks.data_processing.*': {'queue': 'data_processing'},
    'backend.tasks.scheduled_tasks.*': {'queue': 'scheduled'},
    'backend.tasks.data_sync_tasks.*': {'queue': 'data_sync'},
    'extract_product_images': {'queue': 'data_processing'},  # 图片提取任务
}
```

**模块包含配置**（`backend/celery_app.py`）：

```python
include=[
    "backend.tasks.data_processing",
    "backend.tasks.scheduled_tasks",
    "backend.tasks.data_sync_tasks",
    "backend.tasks.image_extraction",  # ⭐ 图片提取任务模块（必须包含）
]
```

**注意**：

- 所有队列都已配置路由规则，确保任务正确路由
- ⚠️ **重要**：所有任务模块必须包含在 `include` 列表中，否则 worker 无法加载任务
- 如果某些队列不需要，可以从启动命令中移除，但需要同时移除对应的路由规则

## Impact

### 受影响的代码位置

| 类型            | 文件数 | 修改点数 | 优先级 |
| --------------- | ------ | -------- | ------ |
| Celery 任务模块 | 1      | 200+     | P0     |
| Celery 配置     | 1      | 50+      | P0     |
| 数据同步路由    | 1      | 100+     | P0     |
| Nginx 配置      | 1      | 50+      | P1     |
| 缓存服务        | 1      | 100+     | P2     |
| 任务优先级      | 2      | 50+      | P3     |
| 限流系统改进    | 3      | 150+     | P1     |
| 监控和告警      | 4      | 200+     | P1     |
| 部署配置优化    | 1      | 20+      | P2     |

### 性能预期

| 指标       | 当前（内存任务）    | 迁移后（Celery）    | 提升幅度 |
| ---------- | ------------------- | ------------------- | -------- |
| 任务持久化 | ❌ 服务器重启后丢失 | ✅ 自动恢复         | 100%     |
| 资源隔离   | ❌ 同一进程         | ✅ 独立 worker 进程 | 完全隔离 |
| 水平扩展   | ❌ 无法扩展         | ✅ 可增加 worker    | 无限扩展 |
| 用户隔离   | ❌ 无隔离           | ✅ 用户级别限制     | 完全隔离 |
| 任务优先级 | ❌ 不支持           | ✅ 支持             | 新增功能 |

### 50-100 人生产环境支持

**场景 1：用户 A 提交 100 个文件同步任务**

- **当前**：所有任务在同一个 FastAPI 进程中执行，可能影响其他用户的 API 响应
- **迁移后**：任务在独立的 Celery worker 进程中执行，不影响 API 服务
- **提升**：API 响应时间从 3-10 秒降低到 <100ms

**场景 2：服务器重启**

- **当前**：任务丢失，用户需要重新提交
- **迁移后**：任务持久化在 Redis 中，自动恢复执行
- **提升**：任务恢复率从 0% 提升到 100%

**场景 3：高峰期（50-100 人同时使用）**

- **当前**：所有任务在同一个进程中执行，可能造成资源竞争
- **迁移后**：可以通过增加 Celery worker 来扩展处理能力
- **提升**：处理能力从固定值提升到可扩展（理论上无限）

**场景 4：紧急任务优先执行**

- **当前**：不支持任务优先级
- **迁移后**：支持任务优先级，紧急任务可以优先执行
- **提升**：新增功能，提升业务灵活性

### 架构对比

**当前架构**：

```
前端 → FastAPI (API服务 + 后台任务) → PostgreSQL
       └─ asyncio.create_task() (内存任务)
```

**迁移后架构**：

```
前端 → Nginx (反向代理 + 限流) → FastAPI (API服务) → PostgreSQL
                                    ↓
                              Celery Task (提交任务)
                                    ↓
                              Redis (消息队列 + 持久化)
                                    ↓
                              Celery Worker (独立进程)
                                    ↓
                              PostgreSQL (数据存储)
```

### 风险评估

| 风险               | 严重程度 | 缓解措施                                  |
| ------------------ | -------- | ----------------------------------------- |
| Celery Worker 崩溃 | 高       | 实现自动重启机制，使用 supervisor/systemd |
| Redis 连接失败     | 高       | 实现连接重试机制，添加健康检查            |
| 任务序列化失败     | 中       | 使用 JSON 序列化，避免复杂对象            |
| 任务重复执行       | 中       | 实现任务去重机制，使用任务 ID             |
| 迁移期间功能回归   | 中       | 分阶段迁移，保留旧代码作为备份            |
| 性能下降           | 低       | 充分测试，监控任务执行时间                |

### 部署要求

**新增依赖**：

- Celery（已安装，需要更新配置）
- Redis（已部署，需要验证连接和版本 >= 5.0 以支持任务优先级）
- Nginx（需要安装和配置）
- `nest_asyncio`（可选，如果 Celery worker 已运行事件循环，需要此库）

**新增服务**：

- Celery Worker（需要启动）
- Celery Beat（已启动，用于定时任务）
- Nginx（需要启动）

**资源需求**：

- Redis 内存：建议 1-2GB（用于任务队列和缓存）
- Celery Worker 进程：建议 2-4 个（根据 CPU 核心数）
- Nginx：内存占用 <100MB

**⚠️ 重要配置要求**：

1. **Celery Worker 启动命令**：

   ```bash
   celery -A backend.celery_app worker --loglevel=info --queues=data_sync,scheduled,data_processing --concurrency=4
   ```

   - 必须指定 `--queues` 参数（监听所有需要的队列）
   - 队列说明：
     - `data_sync`: 数据同步任务（主要业务任务）
     - `scheduled`: 定时任务（由 Celery Beat 调度）
     - `data_processing`: 数据处理任务（Excel 处理、图片提取等）
   - 必须指定 `--concurrency` 参数（建议 4 个并发 worker）

2. **Celery 环境变量**（Docker Compose）：

   ```yaml
   environment:
     CELERY_BROKER_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
     CELERY_RESULT_BACKEND: redis://:${REDIS_PASSWORD}@redis:6379/0
   ```

   - ⚠️ **重要**：Celery 使用 `CELERY_BROKER_URL` 和 `CELERY_RESULT_BACKEND`，不是 `REDIS_URL`
   - 必须包含 Redis 密码（与 Redis 服务配置一致）
   - 必须使用 Docker 服务名称（`redis`）而不是 `localhost`

3. **Celery Worker 健康检查**（推荐）：

   ```yaml
   healthcheck:
     # 使用进程检查方式（更可靠），检查 celery worker 进程是否存在
     test: ["CMD-SHELL", "ps aux | grep '[c]elery.*worker' || exit 1"]
     interval: 30s
     timeout: 10s
     retries: 3
     start_period: 40s
   ```

   - 确保 Worker 正常运行后才认为服务就绪
   - 支持 `depends_on` 的 `condition: service_healthy` 依赖
   - 自动检测 Worker 崩溃并触发重启
   - 使用进程检查方式，比 `inspect ping` 更可靠（不依赖 worker 控制接口）

4. **任务路由配置**（重要）：
   ```python
   # backend/celery_app.py
   task_routes={
       'backend.tasks.data_processing.*': {'queue': 'data_processing'},
       'backend.tasks.scheduled_tasks.*': {'queue': 'scheduled'},
       'backend.tasks.data_sync_tasks.*': {'queue': 'data_sync'},
       'extract_product_images': {'queue': 'data_processing'},  # 图片提取任务
   }
   ```
   - ⚠️ **重要**：确保所有任务都有对应的路由规则
   - 图片提取任务（`extract_product_images`）已配置路由到 `data_processing` 队列
   - 启动命令必须包含所有需要的队列

### 回滚计划

如果迁移后出现问题，可以：

1. **快速回滚**：恢复使用 `asyncio.create_task()` 的代码
2. **保留 Celery**：保留 Celery 配置，但不使用（仅用于定时任务）
3. **渐进式迁移**：先迁移部分功能，验证稳定后再迁移其他功能
