# Celery 监控和告警实施文档

> **状态**: 📋 待实施  
> **实施方案**: 方案 A - 使用 Celery Exporter（推荐）  
> **优先级**: P1 - 生产环境必需  
> **预计时间**: 18-24 小时（分阶段实施）  
> **最后更新**: 2026-01-04（漏洞修复）

## 目录

- [概述](#概述)
- [架构设计](#架构设计)
- [实施步骤](#实施步骤)
- [配置清单](#配置清单)
- [测试验证](#测试验证)
- [故障排查](#故障排查)

---

## 概述

### 为什么选择方案 A（Celery Exporter）

**优点**：
- ✅ **零代码侵入**：无需修改现有 Celery 任务代码
- ✅ **自动收集所有指标**：Celery Exporter 自动监听 Celery 事件，收集所有任务指标
- ✅ **维护成本低**：独立服务，易于维护和升级
- ✅ **快速实施**：部署简单，配置快速

**缺点**：
- ⚠️ **需要额外部署服务**：需要运行独立的 Celery Exporter 进程
- ⚠️ **可能收集不需要的指标**：会收集所有 Celery 指标，可能包含不需要的数据

**对比方案 B（自定义埋点）**：
- 方案 B 需要修改任务代码，添加 Prometheus 客户端库
- 方案 B 更灵活，但实施和维护成本更高
- **建议**：先采用方案 A，快速上线；后续如需更精细的控制，再考虑切换到方案 B

---

## 架构设计

### 整体架构

```
┌─────────────────┐
│  Celery Worker  │
│  (执行任务)      │
└────────┬────────┘
         │ 发送事件
         ↓
┌─────────────────┐
│ Celery Exporter │  ← 监听 Celery 事件
│  (独立服务)      │  ← 自动收集指标
│  端口: 9808     │  ← 暴露 /metrics 端点
└────────┬────────┘
         │ HTTP GET /metrics
         ↓
┌─────────────────┐
│   Prometheus     │  ← 定期抓取指标（15秒间隔）
│  (指标存储)      │  ← 评估告警规则
└────────┬────────┘
         │ 触发告警
         ↓
┌─────────────────┐
│ AlertManager    │  ← 接收告警
│  (告警管理)      │  ← 去重、聚合、路由
└────────┬────────┘
         │ 发送通知
         ↓
┌─────────────────┐
│  通知渠道        │  ← 邮件、Webhook、即时消息
│  (邮件/Webhook)  │
└─────────────────┘
```

### 数据流

1. **指标收集**：
   - Celery Worker 执行任务时发送事件（task-started、task-succeeded、task-failed）
   - Celery Exporter 监听这些事件，自动收集指标
   - Celery Exporter 暴露 `/metrics` 端点（Prometheus 格式）

2. **指标抓取**：
   - Prometheus 定期（15秒）抓取 Celery Exporter 的 `/metrics` 端点
   - Prometheus 存储指标数据（保留 15-30 天）

3. **告警评估**：
   - Prometheus 根据告警规则（`alert_rules.yml`）评估指标
   - 当告警条件满足时，Prometheus 发送告警到 AlertManager

4. **告警处理**：
   - AlertManager 接收告警，进行去重、聚合、路由
   - AlertManager 根据路由规则发送通知到不同渠道

---

## 实施步骤

### 阶段 1：部署 Celery Exporter（MVP - 最小可行产品）

#### 步骤 1.1：选择 Celery Exporter 工具

**推荐工具**：
- **`celery-exporter`**：专门为 Prometheus 设计的 Celery 指标导出器
  - GitHub: https://github.com/OvalMoney/celery-exporter
  - 优点：轻量级、专门设计、维护活跃
  - 缺点：需要 Python 环境

- **`flower`**：Celery 监控工具，支持 Prometheus 指标
  - GitHub: https://github.com/mher/flower
  - 优点：功能丰富、Web UI、维护活跃
  - 缺点：功能较多，可能包含不需要的特性

**建议**：使用 `celery-exporter`（更轻量级，专门用于指标导出）

#### 步骤 1.2：安装 Celery Exporter

**方式 A：Docker 部署（推荐）**

```yaml
# docker-compose.prod.yml
services:
  celery-exporter:
    image: ovalmoney/celery-exporter:latest
    container_name: xihong_erp_celery_exporter_prod
    ports:
      - "9808:9808"
    environment:
      # ⚠️ 重要：必须包含 Redis 密码（与 docker-compose.prod.yml 中的 Redis 配置一致）
      - CELERY_BROKER_URL=redis://:${REDIS_PASSWORD:-redis_pass_2025}@redis:6379/0
      - CELERY_BROKER_TRANSPORT_OPTIONS={"priority_steps": [0, 3, 6, 9]}
      - PORT=9808
    depends_on:
      redis:
        condition: service_healthy
    networks:
      - xihong_erp_network
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:9808/metrics"]
      interval: 10s
      timeout: 5s
      retries: 3
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 256M
        reservations:
          cpus: '0.25'
          memory: 128M
```

**方式 B：独立进程部署**

```bash
# 安装
pip install celery-exporter

# 运行
celery-exporter \
  --broker-url=redis://localhost:6379/0 \
  --port=9808
```

#### 步骤 1.3：验证 Celery Exporter 运行

```bash
# 检查服务状态
curl http://localhost:9808/metrics

# 应该返回 Prometheus 格式的指标，例如：
# celery_tasks_total{state="received"} 100
# celery_tasks_total{state="started"} 95
# celery_tasks_total{state="succeeded"} 90
# celery_tasks_total{state="failed"} 5
```

**⚠️ 重要：指标验证步骤**

在配置告警规则之前，必须先验证 Celery Exporter 实际暴露的指标名称：

```bash
# 1. 访问 /metrics 端点，查看所有可用指标
curl http://localhost:9808/metrics | grep celery

# 2. 记录实际指标名称（可能与文档中的示例不同）
# 常见指标：
# - celery_tasks_total{state="..."} - 任务总数（按状态）
# - celery_task_duration_seconds - 任务执行时间（Histogram）
# - celery_workers - Worker 数量
# - celery_queue_length - 队列长度（如果支持）

# 3. 在 Prometheus UI 中查询指标，确认指标数据正常
# http://localhost:9090
# 查询: celery_tasks_total
```

**注意**：不同版本的 Celery Exporter 可能暴露不同的指标名称，必须根据实际指标名称更新告警规则。

---

### 阶段 2：配置 Prometheus 抓取

#### 步骤 2.1：更新 Prometheus 配置

**⚠️ 重要：根据部署环境选择正确的地址**

**方式 A：Docker Compose 部署（推荐）**

```yaml
# monitoring/prometheus.yml
scrape_configs:
  # ... 其他抓取配置 ...

  # Celery Exporter 抓取配置（Docker 网络）
  - job_name: 'celery'
    scrape_interval: 15s
    scrape_timeout: 10s
    static_configs:
      - targets: ['celery-exporter:9808']  # Docker 服务名称
        labels:
          job: 'celery'
          component: 'task-queue'
          instance: 'celery-exporter'
```

**方式 B：独立进程部署**

```yaml
# monitoring/prometheus.yml
scrape_configs:
  # ... 其他抓取配置 ...

  # Celery Exporter 抓取配置（本地网络）
  - job_name: 'celery'
    scrape_interval: 15s
    scrape_timeout: 10s
    static_configs:
      - targets: ['localhost:9808']  # 本地地址
        labels:
          job: 'celery'
          component: 'task-queue'
          instance: 'celery-exporter'
```

**注意**：如果 Prometheus 也在 Docker 网络中，使用服务名称（如 `celery-exporter:9808`）；如果 Prometheus 在主机上运行，使用 `localhost:9808`。

#### 步骤 2.2：验证 Prometheus 配置

```bash
# 检查配置文件语法
promtool check config monitoring/prometheus.yml

# 重启 Prometheus（如果使用 Docker）
docker-compose restart prometheus

# 在 Prometheus UI 中查询指标
# http://localhost:9090
# 查询: celery_tasks_total
```

---

### 阶段 3：添加告警规则

#### 步骤 3.1：设计告警规则

**告警规则设计原则**：
- **任务失败率告警**：失败率 >10%，持续 5 分钟 → Warning
- **任务队列长度告警**：队列长度 >100，持续 5 分钟 → Warning
- **任务执行时间告警**：P95 执行时间 >30 分钟，持续 10 分钟 → Warning
- **Worker 状态告警**：Worker 离线，持续 2 分钟 → Critical
- **Redis 连接失败告警**：连接失败，立即告警 → Critical

#### 步骤 3.2：更新告警规则文件

**⚠️ 重要：告警规则中的指标名称必须与实际指标匹配**

在添加告警规则之前，必须先验证 Celery Exporter 实际暴露的指标名称（参见步骤 1.3）。

```yaml
# monitoring/alert_rules.yml
groups:
  - name: celery_alerts
    interval: 30s
    rules:
      # 任务失败率告警
      # ⚠️ 注意：指标名称可能需要根据实际 Celery Exporter 版本调整
      - alert: HighCeleryTaskFailureRate
        expr: |
          rate(celery_tasks_total{state="failed"}[5m]) /
          rate(celery_tasks_total{state="received"}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
          component: celery
        annotations:
          summary: "Celery 任务失败率过高"
          description: "任务失败率 {{ $value | humanizePercentage }}，超过阈值 10%（初始阈值，需根据实际情况调整）"

      # 任务队列长度告警
      # ⚠️ 注意：如果 celery_queue_length 指标不存在，需要：
      # 1. 使用其他指标（如 celery_tasks_total{state="pending"}）
      # 2. 或移除此告警规则
      - alert: HighCeleryQueueLength
        expr: |
          # 方案 A：如果存在 celery_queue_length 指标
          celery_queue_length > 100
          # 方案 B：如果不存在，使用任务总数估算（需要根据实际情况调整）
          # sum(celery_tasks_total{state="pending"}) > 100
        for: 5m
        labels:
          severity: warning
          component: celery
        annotations:
          summary: "Celery 任务队列长度过高"
          description: "队列长度 {{ $value }}，超过阈值 100（初始阈值，需根据实际情况调整）"

      # 任务执行时间告警
      # ⚠️ 注意：如果 celery_task_duration_seconds 指标不存在，需要：
      # 1. 使用其他指标（如 celery_task_runtime_seconds）
      # 2. 或移除此告警规则
      - alert: HighCeleryTaskExecutionTime
        expr: |
          # 方案 A：如果存在 histogram 指标
          histogram_quantile(0.95,
            rate(celery_task_duration_seconds_bucket[10m])
          ) > 1800
          # 方案 B：如果不存在 histogram，使用 summary 指标（需要根据实际情况调整）
          # celery_task_duration_seconds{quantile="0.95"} > 1800
        for: 10m
        labels:
          severity: warning
          component: celery
        annotations:
          summary: "Celery 任务执行时间过长"
          description: "P95 执行时间 {{ $value }}s，超过阈值 1800s（初始阈值，需根据实际情况调整）"

      # Worker 状态告警
      - alert: CeleryWorkerDown
        expr: up{job="celery"} == 0
        for: 2m
        labels:
          severity: critical
          component: celery
        annotations:
          summary: "Celery Worker 离线"
          description: "Celery Exporter 无法连接，Worker 可能已离线"

      # Redis 连接失败告警
      # ⚠️ 注意：如果 celery_broker_connection_failures_total 指标不存在，需要：
      # 1. 使用其他指标（如检查 Celery Exporter 的 up 状态）
      # 2. 或移除此告警规则，依赖 Worker 状态告警
      - alert: CeleryRedisConnectionFailed
        expr: |
          # 方案 A：如果存在连接失败指标
          celery_broker_connection_failures_total > 0
          # 方案 B：如果不存在，使用 Exporter 状态（需要根据实际情况调整）
          # up{job="celery"} == 0
        for: 0m
        labels:
          severity: critical
          component: celery
        annotations:
          summary: "Celery Redis 连接失败"
          description: "Redis 连接失败次数 {{ $value }}"
```

**⚠️ 告警阈值调整说明**：

- 所有告警阈值（失败率 10%、队列长度 100、执行时间 1800s）都是**初始值**
- 建议先设置较宽松的阈值，观察 1-2 周后再根据实际情况调整
- 不同业务场景可能需要不同的阈值

#### 步骤 3.3：验证告警规则

```bash
# 检查告警规则语法
promtool check rules monitoring/alert_rules.yml

# 在 Prometheus UI 中验证规则
# http://localhost:9090/alerts
```

---

### 阶段 4：配置 AlertManager

#### 步骤 4.1：部署 AlertManager

**方式 A：Docker 部署（推荐）**

```yaml
# docker-compose.prod.yml
services:
  alertmanager:
    image: prom/alertmanager:latest
    container_name: xihong_erp_alertmanager_prod
    ports:
      - "9093:9093"
    environment:
      # ⚠️ 重要：SMTP 密码等敏感信息通过环境变量提供
      - SMTP_HOST=${SMTP_HOST:-smtp.example.com:587}
      - SMTP_FROM=${SMTP_FROM:-alerts@example.com}
      - SMTP_USERNAME=${SMTP_USERNAME:-alerts@example.com}
      - SMTP_PASSWORD=${SMTP_PASSWORD}  # 必须设置
    volumes:
      - ./monitoring/alertmanager.yml:/etc/alertmanager/alertmanager.yml
      - alertmanager_data:/alertmanager
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'
      - '--storage.path=/alertmanager'
    depends_on:
      - prometheus
    networks:
      - xihong_erp_network
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:9093/-/healthy"]
      interval: 10s
      timeout: 5s
      retries: 3
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 256M
        reservations:
          cpus: '0.25'
          memory: 128M
```

**方式 B：独立进程部署**

```bash
# 下载 AlertManager
wget https://github.com/prometheus/alertmanager/releases/download/v0.27.0/alertmanager-0.27.0.linux-amd64.tar.gz
tar xzf alertmanager-0.27.0.linux-amd64.tar.gz
cd alertmanager-0.27.0.linux-amd64

# 运行
./alertmanager --config.file=monitoring/alertmanager.yml
```

#### 步骤 4.2：配置 AlertManager

**⚠️ 重要：使用环境变量管理敏感信息（密码、API Key）**

```yaml
# monitoring/alertmanager.yml
global:
  resolve_timeout: 5m
  # SMTP 配置（使用环境变量，避免硬编码密码）
  smtp_smarthost: '${SMTP_HOST:-smtp.example.com:587}'
  smtp_from: '${SMTP_FROM:-alerts@example.com}'
  smtp_auth_username: '${SMTP_USERNAME:-alerts@example.com}'
  smtp_auth_password: '${SMTP_PASSWORD}'  # ⚠️ 必须通过环境变量提供

# 路由规则
route:
  group_by: ['alertname', 'severity', 'component']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'default'
  routes:
    # Critical 告警路由到 critical 接收器
    - match:
        severity: critical
      receiver: 'critical'
    # Warning 告警路由到 warning 接收器
    - match:
        severity: warning
      receiver: 'warning'

# 接收器配置
receivers:
  - name: 'default'
    email_configs:
      - to: 'ops-team@example.com'
        headers:
          Subject: '{{ .GroupLabels.alertname }}'

  - name: 'critical'
    email_configs:
      - to: 'critical-alerts@example.com'
        headers:
          Subject: '[CRITICAL] {{ .GroupLabels.alertname }}'
    # Webhook 通知（可选）
    webhook_configs:
      - url: 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
        send_resolved: true

  - name: 'warning'
    email_configs:
      - to: 'warning-alerts@example.com'
        headers:
          Subject: '[WARNING] {{ .GroupLabels.alertname }}'

# 抑制规则（可选）
inhibit_rules:
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['alertname', 'component']
```

#### 步骤 4.3：更新 Prometheus 配置

**⚠️ 重要：根据部署环境选择正确的地址**

**方式 A：Docker Compose 部署（推荐）**

```yaml
# monitoring/prometheus.yml
alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - 'alertmanager:9093'  # Docker 服务名称
```

**方式 B：独立进程部署**

```yaml
# monitoring/prometheus.yml
alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - 'localhost:9093'  # 本地地址
```

**注意**：如果 Prometheus 也在 Docker 网络中，使用服务名称（如 `alertmanager:9093`）；如果 Prometheus 在主机上运行，使用 `localhost:9093`。

#### 步骤 4.4：验证 AlertManager

```bash
# 检查 AlertManager 配置
amtool check-config monitoring/alertmanager.yml

# 启动 AlertManager
docker-compose up -d alertmanager

# 访问 AlertManager UI
# http://localhost:9093
```

---

### 阶段 5：测试验证

#### 步骤 5.1：功能测试

**测试指标收集**：
```bash
# 1. 提交测试任务
curl -X POST http://localhost:8000/api/data-sync/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"platform": "shopee", "account_id": "test"}'

# 2. 等待任务执行
sleep 10

# 3. 查询 Prometheus 指标
curl 'http://localhost:9090/api/v1/query?query=celery_tasks_total'

# 4. 验证指标更新
# 应该看到任务数量增加
```

**测试告警触发**：
```bash
# 1. 模拟高失败率（需要修改任务代码或使用测试工具）
# 2. 等待告警触发（5 分钟）
# 3. 检查 AlertManager UI
# http://localhost:9093

# 4. 验证告警通知
# 检查邮箱或 Webhook 是否收到通知
```

**测试告警恢复**：
```bash
# 1. 恢复正常状态
# 2. 等待告警恢复（根据 for 参数）
# 3. 验证恢复通知（如果配置了 send_resolved）
```

#### 步骤 5.2：性能测试

**测试监控性能影响**：
```bash
# 1. 关闭监控，运行性能测试
# 2. 开启监控，运行性能测试
# 3. 对比性能差异（应该 <5%）
```

**测试 Prometheus 存储**：
```bash
# 1. 检查 Prometheus 数据目录大小
du -sh /var/lib/prometheus

# 2. 验证数据保留策略
# 在 prometheus.yml 中配置 retention: 15d
```

---

## 配置清单

### 需要创建的文件

1. **`monitoring/celery_exporter.yml`**（可选，如果需要自定义配置）
   - Celery Exporter 配置文件

2. **`monitoring/alertmanager.yml`**
   - AlertManager 配置文件（必须）

3. **`docs/monitoring/CELERY_MONITORING_GUIDE.md`**
   - Celery 监控使用指南

4. **`docs/monitoring/ALERT_HANDLING_GUIDE.md`**
   - 告警处理指南

### 需要修改的文件

1. **`monitoring/prometheus.yml`**
   - 添加 Celery Exporter 抓取配置
   - 添加 AlertManager 地址配置

2. **`monitoring/alert_rules.yml`**
   - 添加 Celery 告警规则组

3. **`docker-compose.prod.yml`**
   - 添加 celery-exporter 服务
   - 添加 alertmanager 服务
   - 添加 grafana 服务（可选）

4. **`docs/deployment/PRODUCTION_DEPLOYMENT_GUIDE.md`**
   - 添加监控部署说明

5. **`docs/DEVELOPMENT_RULES/DEPLOYMENT.md`**
   - 更新监控和告警章节

---

## 测试验证

### 验证清单

#### 指标收集验证

- [ ] Celery Exporter 服务正常运行
- [ ] `/metrics` 端点可访问
- [ ] Prometheus 能抓取到指标
- [ ] 指标数据格式正确
- [ ] 指标值实时更新
- [ ] 指标标签正确

#### 告警规则验证

- [ ] 告警规则语法正确
- [ ] 告警规则已加载到 Prometheus
- [ ] 告警条件能正确触发
- [ ] 告警持续时间（for）生效
- [ ] 告警恢复机制正常

#### 通知验证

- [ ] AlertManager 服务正常运行
- [ ] 告警能正确路由
- [ ] 邮件通知发送成功
- [ ] Webhook 通知调用成功（如配置）
- [ ] 告警消息内容正确
- [ ] 告警去重机制正常

#### 性能验证

- [ ] 监控对系统性能影响 <5%
- [ ] Prometheus 存储性能正常
- [ ] 告警评估性能正常（<1秒）

---

## 故障排查

### 常见问题

#### 1. Celery Exporter 无法连接 Redis

**症状**：Celery Exporter 启动失败，日志显示连接错误

**排查步骤**：
1. 检查 Redis 服务是否运行
2. 检查 `CELERY_BROKER_URL` 配置是否正确
3. 检查网络连接（Docker 网络配置）
4. 检查 Redis 密码配置（如使用）

**解决方案**：
```bash
# 检查 Redis 连接
redis-cli -h localhost -p 6379 ping

# 检查 Celery Exporter 配置
docker-compose logs celery-exporter
```

#### 2. Prometheus 无法抓取指标

**症状**：Prometheus UI 中查询不到 Celery 指标

**排查步骤**：
1. 检查 Celery Exporter 是否运行
2. 检查 `/metrics` 端点是否可访问
3. 检查 Prometheus 配置中的 target 地址是否正确
4. 检查 Prometheus 日志

**解决方案**：
```bash
# 检查 Celery Exporter 状态
curl http://localhost:9808/metrics

# 检查 Prometheus 配置
promtool check config monitoring/prometheus.yml

# 检查 Prometheus 日志
docker-compose logs prometheus
```

#### 3. 告警规则不触发

**症状**：告警条件满足，但告警未触发

**排查步骤**：
1. 检查告警规则语法
2. 检查 PromQL 表达式是否正确
3. 检查告警持续时间（for）是否满足
4. 在 Prometheus UI 中手动执行 PromQL 查询

**解决方案**：
```bash
# 检查告警规则语法
promtool check rules monitoring/alert_rules.yml

# 在 Prometheus UI 中测试 PromQL
# http://localhost:9090
# 查询: rate(celery_tasks_total{state="failed"}[5m])
```

#### 4. AlertManager 未收到告警

**症状**：Prometheus 显示告警已触发，但 AlertManager 未收到

**排查步骤**：
1. 检查 Prometheus 配置中的 AlertManager 地址
2. 检查 AlertManager 服务是否运行
3. 检查网络连接
4. 检查 AlertManager 日志

**解决方案**：
```bash
# 检查 AlertManager 状态
curl http://localhost:9093/-/healthy

# 检查 Prometheus 配置
grep alertmanagers monitoring/prometheus.yml

# 检查 AlertManager 日志
docker-compose logs alertmanager
```

#### 5. 通知未发送

**症状**：AlertManager 收到告警，但通知未发送

**排查步骤**：
1. 检查 AlertManager 配置中的通知渠道配置
2. 检查 SMTP 服务器配置（邮件通知）
3. 检查 Webhook URL 配置（Webhook 通知）
4. 检查 AlertManager 日志

**解决方案**：
```bash
# 检查 AlertManager 配置
amtool check-config monitoring/alertmanager.yml

# 测试邮件发送（手动）
# 测试 Webhook 调用（手动）

# 检查 AlertManager 日志
docker-compose logs alertmanager
```

---

## 回滚计划

如果监控和告警实施失败或需要回滚，按以下步骤操作：

### 快速回滚步骤

1. **停止监控服务**：
   ```bash
   # Docker Compose
   docker-compose stop celery-exporter alertmanager prometheus grafana
   
   # 或删除服务
   docker-compose rm -f celery-exporter alertmanager prometheus grafana
   ```

2. **恢复 Prometheus 配置**：
   ```bash
   # 备份当前配置
   cp monitoring/prometheus.yml monitoring/prometheus.yml.backup
   
   # 恢复原始配置（移除 Celery 抓取配置和 AlertManager 配置）
   git checkout monitoring/prometheus.yml
   ```

3. **恢复告警规则**：
   ```bash
   # 备份当前规则
   cp monitoring/alert_rules.yml monitoring/alert_rules.yml.backup
   
   # 恢复原始规则（移除 Celery 告警规则组）
   git checkout monitoring/alert_rules.yml
   ```

4. **重启 Prometheus**：
   ```bash
   docker-compose restart prometheus
   ```

5. **验证系统正常运行**：
   ```bash
   # 检查 Celery Worker 是否正常运行
   celery -A backend.celery_app inspect active
   
   # 检查 API 服务是否正常
   curl http://localhost:8000/health
   ```

### 保留监控但禁用告警

如果只需要禁用告警，保留监控：

1. **移除告警规则**：
   ```bash
   # 在 monitoring/alert_rules.yml 中注释掉 celery_alerts 规则组
   # 或删除整个规则组
   ```

2. **重启 Prometheus**：
   ```bash
   docker-compose restart prometheus
   ```

### 清理监控数据

如果需要清理 Prometheus 数据：

```bash
# 停止 Prometheus
docker-compose stop prometheus

# 删除数据卷（⚠️ 警告：会删除所有监控数据）
docker volume rm <prometheus_data_volume>

# 重启 Prometheus（会重新创建数据卷）
docker-compose up -d prometheus
```

---

## 总结

### 实施优先级

1. **第一阶段（MVP）**：部署 Celery Exporter + Prometheus + 基础告警规则 + 邮件通知
   - 预计时间：6-8 小时
   - 优先级：P0

2. **第二阶段（增强）**：部署 AlertManager + 优化告警规则 + 多渠道通知
   - 预计时间：4-6 小时
   - 优先级：P1

3. **第三阶段（优化）**：部署 Grafana + 创建仪表板 + 文档完善
   - 预计时间：4-6 小时
   - 优先级：P2

### 关键成功因素

- ✅ **零代码侵入**：使用 Celery Exporter，无需修改任务代码
- ✅ **快速实施**：独立服务，部署简单
- ✅ **自动收集**：自动收集所有 Celery 指标
- ✅ **易于维护**：标准 Prometheus 生态，维护成本低

### 后续优化方向

- 📊 **自定义指标**：如需更精细的控制，可切换到方案 B（自定义埋点）
- 📈 **高级告警**：告警聚合、抑制、路由优化
- 🎨 **可视化增强**：创建更多 Grafana 仪表板
- 🔍 **日志关联**：将告警与日志系统关联，便于故障排查

