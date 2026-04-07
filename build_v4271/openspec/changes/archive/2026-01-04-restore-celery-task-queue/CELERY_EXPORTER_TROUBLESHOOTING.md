# Celery Exporter 故障排查指南

> **日期**: 2026-01-04  
> **问题**: Celery Exporter 显示 unhealthy  
> **状态**: 排查中

---

## 🔍 当前状态

- **容器状态**: 运行中
- **健康检查**: unhealthy
- **Redis 连接**: ✅ 正常（已验证）
- **指标端点**: ⚠️ 待验证

---

## 📋 排查步骤

### 1. 检查 Celery Worker 是否运行

**问题**: Celery Exporter 需要 Celery Worker 运行才能收集指标

**检查命令**:
```bash
docker ps | Select-String "celery-worker"
```

**如果未运行**:
```bash
# 启动 Celery Worker
docker-compose -f docker-compose.prod.yml up -d celery-worker

# 检查启动日志
docker logs xihong_erp_celery_worker_prod
```

### 2. 检查 Celery Exporter 日志

**查看日志**:
```bash
docker logs xihong-celery-exporter --tail 50
```

**常见错误**:
- Redis 连接失败
- Celery Worker 未运行
- 配置错误

### 3. 测试指标端点

**从容器内部测试**:
```bash
docker exec xihong-celery-exporter wget -q -O- http://localhost:9808/metrics
```

**从主机测试**:
```powershell
Invoke-WebRequest -Uri http://localhost:9808/metrics -UseBasicParsing
```

**预期结果**: 应该返回 Prometheus 格式的指标数据

### 4. 检查健康检查配置

**当前配置**:
```yaml
healthcheck:
  test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:9808/metrics"]
  interval: 10s
  timeout: 5s
  retries: 3
  start_period: 10s
```

**可能问题**:
- `wget` 命令可能不可用
- 指标端点可能启动较慢
- 需要更长的 `start_period`

### 5. 检查网络连接

**验证网络**:
```bash
# 检查容器网络
docker network inspect xihong_erp_network

# 检查 Celery Exporter 网络
docker inspect xihong-celery-exporter --format='{{range $net, $conf := .NetworkSettings.Networks}}{{$net}} {{end}}'
```

---

## 🔧 解决方案

### 方案 1: 启动 Celery Worker

如果 Celery Worker 未运行，需要启动它：

```bash
docker-compose -f docker-compose.prod.yml up -d celery-worker celery-beat
```

### 方案 2: 修改健康检查配置

如果指标端点启动较慢，可以增加 `start_period`:

```yaml
healthcheck:
  test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:9808/metrics"]
  interval: 10s
  timeout: 5s
  retries: 3
  start_period: 30s  # 增加到 30 秒
```

### 方案 3: 使用 curl 替代 wget

如果 `wget` 不可用，可以使用 `curl`:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:9808/metrics"]
  interval: 10s
  timeout: 5s
  retries: 3
  start_period: 30s
```

### 方案 4: 禁用健康检查（临时）

如果健康检查一直失败但不影响功能，可以临时禁用：

```yaml
# 注释掉 healthcheck 配置
# healthcheck:
#   test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:9808/metrics"]
```

---

## 📊 验证步骤

### 1. 验证 Celery Worker 运行

```bash
docker ps | Select-String "celery-worker"
docker logs xihong_erp_celery_worker_prod --tail 20
```

### 2. 验证指标端点

```bash
# 从容器内部
docker exec xihong-celery-exporter wget -q -O- http://localhost:9808/metrics | head -20

# 从主机
curl http://localhost:9808/metrics
```

### 3. 验证 Prometheus 抓取

访问 http://localhost:19090，查询：
- `up{job="celery"}` - 应该返回 1
- `celery_tasks_total` - 应该返回任务指标

---

## 📝 检查清单

- [ ] Celery Worker 是否运行？
- [ ] Celery Exporter 能否连接到 Redis？
- [ ] 指标端点 `/metrics` 是否可访问？
- [ ] Prometheus 能否抓取指标？
- [ ] 健康检查配置是否正确？

---

## 🔗 相关文档

- [部署检查报告](PHASE6_DEPLOYMENT_CHECK_REPORT.md)
- [完成总结](PHASE6_COMPLETE_SUMMARY.md)
- [待完成工作](REMAINING_WORK_SUMMARY.md)

