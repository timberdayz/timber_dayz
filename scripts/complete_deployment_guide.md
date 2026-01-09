# 完整部署指南

**更新时间**: 2025-01-09  
**状态**: ✅ 所有服务（除 pgadmin）都已配置 profiles

## ✅ 已修复的服务

### 1. 核心服务（docker-compose.prod.yml）

所有服务都有 `profiles: [production, full]`：

- ✅ postgres
- ✅ redis
- ✅ backend
- ✅ frontend
- ✅ nginx
- ✅ celery-worker
- ✅ celery-beat
- ✅ celery-exporter（已修复）

### 2. 监控服务（docker/docker-compose.monitoring.yml）

所有服务都已添加 `profiles: [production, full]`：

- ✅ prometheus
- ✅ grafana
- ✅ alertmanager
- ✅ postgres-exporter
- ✅ celery-exporter

### 3. Metabase（docker-compose.metabase.yml）

已有 `profiles: [production, full]`：

- ✅ metabase

### 4. pgAdmin（开发工具，生产环境不需要）

- ❌ profiles: `[dev, full]`（没有 production）
- **说明**: 这是开发工具，生产环境不需要

## 🚀 部署命令

### 方案1：只部署核心服务（最小化部署）

```bash
docker-compose --env-file .env \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.cloud.yml \
  --profile production up -d
```

**会启动的服务** (8个):
- postgres
- redis
- backend
- frontend
- nginx
- celery-worker
- celery-beat
- celery-exporter

### 方案2：核心服务 + Metabase（推荐生产环境）

```bash
docker-compose --env-file .env \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.cloud.yml \
  -f docker-compose.metabase.yml \
  --profile production up -d
```

**会启动的服务** (9个):
- 核心服务 (8个)
- metabase

### 方案3：完整部署（核心 + Metabase + 监控）

```bash
docker-compose --env-file .env \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.cloud.yml \
  -f docker-compose.metabase.yml \
  -f docker/docker-compose.monitoring.yml \
  --profile production up -d
```

**会启动的服务** (14个):
- 核心服务 (8个)
- metabase
- prometheus
- grafana
- alertmanager
- postgres-exporter
- celery-exporter（监控版本，会与核心版本冲突，建议只启动一个）

**注意**: celery-exporter 在两个文件中都有定义，建议只使用一个。

## 📊 服务列表总结

| 服务 | 配置文件 | Profiles | 状态 |
|------|----------|----------|------|
| postgres | docker-compose.prod.yml | ✅ production, full | 已修复 |
| redis | docker-compose.prod.yml | ✅ dev, production, full | 已修复 |
| backend | docker-compose.prod.yml | ✅ production, full | 已有 |
| frontend | docker-compose.prod.yml | ✅ production, full | 已有 |
| nginx | docker-compose.prod.yml | ✅ production, full | 已有 |
| celery-worker | docker-compose.prod.yml | ✅ production, full | 已有 |
| celery-beat | docker-compose.prod.yml | ✅ production, full | 已有 |
| celery-exporter | docker-compose.prod.yml | ✅ production, full | 已修复 |
| metabase | docker-compose.metabase.yml | ✅ dev, production, full | 已有 |
| prometheus | docker/docker-compose.monitoring.yml | ✅ production, full | 已修复 |
| grafana | docker/docker-compose.monitoring.yml | ✅ production, full | 已修复 |
| alertmanager | docker/docker-compose.monitoring.yml | ✅ production, full | 已修复 |
| postgres-exporter | docker/docker-compose.monitoring.yml | ✅ production, full | 已修复 |
| celery-exporter | docker/docker-compose.monitoring.yml | ✅ production, full | 已修复 |
| pgadmin | docker-compose.yml | ⚠️ dev, full | 开发工具 |

## ⚠️ 注意事项

### 1. celery-exporter 重复定义

`celery-exporter` 在两个文件中都有定义：
- `docker-compose.prod.yml`（核心版本）
- `docker/docker-compose.monitoring.yml`（监控版本）

**建议**: 只使用一个版本，避免冲突。推荐使用 `docker-compose.prod.yml` 中的版本。

如果使用完整部署方案3，需要从监控配置中移除 celery-exporter，或者只启动核心版本。

### 2. 网络配置

所有服务都使用统一的网络 `erp_network`，确保服务间可以互相通信。

### 3. 资源限制

所有服务都配置了资源限制（CPU 和内存），适合 2核4G 服务器。

## ✅ 验证

### 验证配置

```bash
# 验证核心服务
docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile production config

# 验证监控服务
docker-compose -f docker/docker-compose.monitoring.yml --profile production config

# 验证 Metabase
docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.metabase.yml --profile production config
```

### 检查服务状态

```bash
docker ps --filter "name=xihong_erp" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

## 🎉 修复完成

**所有服务（除 pgadmin）都已配置 profiles，可以通过 `--profile production` 自动部署！**
