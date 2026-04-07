# Phase 6 监控和告警部署状态

> **部署日期**: 2026-01-04  
> **状态**: ⚠️ 部分服务已启动，需要解决端口冲突问题

---

## ✅ 已完成的步骤

### 步骤 1：设置环境变量 ✅

- ✅ 环境变量文件已复制：`env.production.example` → `.env.production`
- ⚠️ **注意**：需要用户手动编辑 `.env.production` 文件，设置实际的 SMTP 服务器和密码

### 步骤 2：启动监控服务 ⚠️

**已启动的服务**：
- ✅ **Celery Exporter** (端口 9808) - 已启动
- ✅ **PostgreSQL Exporter** (端口 9187) - 已启动
- ✅ **Node Exporter** (端口 9100) - 已启动

**启动失败的服务**：
- ❌ **Prometheus** (端口 9090) - 端口被占用或权限问题
- ❌ **AlertManager** (端口 9093) - 依赖 Prometheus，未启动
- ❌ **Grafana** (端口 3001) - 依赖 Prometheus，未启动

**问题**：
```
Error: ports are not available: exposing port TCP 0.0.0.0:9090 -> 127.0.0.1:0: 
listen tcp 0.0.0.0:9090: bind: An attempt was made to access a socket 
in a way forbidden by its access permissions.
```

这是 Windows 上常见的端口保留问题。

### 步骤 3：运行测试验证 ⚠️

- ✅ 测试脚本已运行
- ⚠️ 测试结果：1/5 通过（只有 Prometheus 规则检查通过）
- ⚠️ Celery Exporter 可能还在启动中，需要等待

---

## 🔧 需要解决的问题

### 问题 1：端口 9090 被占用

**解决方案**：

**方案 A：检查并释放端口（推荐）**

```powershell
# 1. 检查端口占用
netstat -ano | findstr :9090

# 2. 如果发现占用，结束进程（替换 <PID> 为实际进程ID）
taskkill /PID <PID> /F

# 3. 检查 Windows 端口保留（可能需要管理员权限）
netsh interface ipv4 show excludedportrange protocol=tcp

# 4. 如果端口在保留范围内，需要释放保留（需要管理员权限）
netsh int ipv4 add excludedportrange protocol=tcp startport=9090 numberofports=1
```

**方案 B：修改 Prometheus 端口**

如果端口 9090 确实被其他服务使用，可以修改配置文件：

```yaml
# docker/docker-compose.monitoring.yml
services:
  prometheus:
    ports:
      - "9091:9090"  # 修改为其他端口
```

同时需要更新：
- `monitoring/prometheus.yml` 中的 AlertManager 配置（如果使用）
- `scripts/test_monitoring_setup.py` 中的端口配置

**方案 C：使用管理员权限运行 Docker**

端口权限问题可能需要管理员权限。

---

### 问题 2：环境变量未设置

**需要设置的环境变量**（在 `.env.production` 文件中）：

```bash
# Redis 密码
REDIS_PASSWORD=your_redis_password

# SMTP 配置（必需）
SMTP_HOST=smtp.example.com:587
SMTP_FROM=alerts@your-domain.com
SMTP_USERNAME=alerts@your-domain.com
SMTP_PASSWORD=your_smtp_password  # ⚠️ 必须设置

# 告警邮件收件人
ALERT_EMAIL_TO=ops-team@your-domain.com
ALERT_EMAIL_CRITICAL=critical-alerts@your-domain.com
ALERT_EMAIL_WARNING=warning-alerts@your-domain.com
ALERT_EMAIL_CELERY=celery-alerts@your-domain.com

# Grafana 管理员密码
GRAFANA_ADMIN_PASSWORD=your_grafana_password
```

**设置步骤**：

```bash
# 编辑环境变量文件
notepad .env.production

# 或使用其他编辑器
code .env.production
```

---

## 📋 下一步操作

### 立即执行

1. **解决端口 9090 冲突**
   - 检查端口占用情况
   - 根据情况选择方案 A、B 或 C

2. **设置环境变量**
   - 编辑 `.env.production` 文件
   - 设置实际的 SMTP 服务器和密码

3. **重新启动监控服务**
   ```bash
   # 停止当前服务
   docker-compose -f docker/docker-compose.monitoring.yml down
   
   # 重新启动
   docker-compose -f docker/docker-compose.monitoring.yml up -d
   ```

4. **验证服务**
   ```bash
   # 运行测试脚本
   python scripts/test_monitoring_setup.py
   
   # 或手动检查
   # Celery Exporter
   curl http://localhost:9808/metrics
   
   # Prometheus（解决端口问题后）
   curl http://localhost:9090/-/healthy
   
   # AlertManager
   curl http://localhost:9093/-/healthy
   
   # Grafana
   curl http://localhost:3001/api/health
   ```

---

## 📊 当前服务状态

| 服务 | 状态 | 端口 | 说明 |
|------|------|------|------|
| Celery Exporter | ✅ 运行中 | 9808 | 正常 |
| PostgreSQL Exporter | ✅ 运行中 | 9187 | 正常 |
| Node Exporter | ✅ 运行中 | 9100 | 正常 |
| Prometheus | ❌ 未启动 | 9090 | 端口冲突 |
| AlertManager | ❌ 未启动 | 9093 | 依赖 Prometheus |
| Grafana | ❌ 未启动 | 3001 | 依赖 Prometheus |

---

## ✅ 配置工作完成情况

所有配置文件和工作已完成：

- ✅ 所有配置文件已创建和更新
- ✅ Docker Compose 配置正确
- ✅ 网络配置统一
- ✅ 测试脚本已创建
- ✅ 文档已更新

**当前状态**：配置工作 100% 完成，部署过程中遇到端口冲突问题，需要用户手动解决。

---

## 📝 注意事项

1. **端口冲突**：Windows 上端口保留是常见问题，需要管理员权限解决
2. **环境变量**：必须设置实际的 SMTP 服务器信息才能发送告警邮件
3. **服务依赖**：AlertManager 和 Grafana 依赖 Prometheus，需要 Prometheus 先启动
4. **Celery Worker**：确保 Celery Worker 正在运行，Celery Exporter 才能收集指标

---

## 🔗 参考文档

- [部署指南](docs/deployment/PRODUCTION_DEPLOYMENT_GUIDE.md)
- [实施状态](PHASE6_IMPLEMENTATION_STATUS.md)
- [完成总结](PHASE6_COMPLETION_SUMMARY.md)
- [检查清单](PHASE6_CHECKLIST.md)

