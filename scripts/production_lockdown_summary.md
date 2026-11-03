# 生产环境最小端口暴露配置总结

> ⚠️ **历史手工操作记录，非当前发布路径**（2026-11-03 标注）
> 生产实际生效的 compose 组合以 `scripts/deploy_remote_production.sh` 为准 ——
> **该脚本从不引用 `docker-compose.prod.lockdown.yml`**。
> 详见 `docs/guides/RELEASE_CHECKLIST.md` 的 "Production Compose Combination"。

**创建时间**: 2025-01-09  
**状态**: ✅ 配置完成并验证通过

## ✅ 配置完成

### 已创建的文件

1. **`docker-compose.prod.lockdown.yml`**
   - 锁定核心服务端口（PostgreSQL、Redis、Backend、Frontend、Celery Exporter）
   - 保留 Nginx 的 80/443 端口

2. **`docker-compose.metabase.lockdown.yml`**
   - Metabase 绑定到 `127.0.0.1:8080`，仅本地访问

3. **`scripts/production_lockdown_deployment_guide.md`**
   - 完整的部署指南和说明文档

4. **`scripts/test_production_lockdown.py`**
   - 端口锁定配置验证脚本

## 📊 端口映射对比

### 修改前（不安全）
| 服务 | 宿主机端口 | 状态 |
|------|-----------|------|
| postgres | 5432 | ❌ 对外暴露 |
| redis | 6379 | ❌ 对外暴露 |
| backend | 8000 | ❌ 对外暴露 |
| frontend | 3000 | ❌ 对外暴露 |
| nginx | 80, 443 | ✅ 需要暴露 |
| celery-exporter | 9808 | ❌ 对外暴露 |
| metabase | 8080 | ❌ 对外暴露 |

**总计**: 7 个对外暴露端口

### 修改后（安全）
| 服务 | 宿主机端口 | 状态 |
|------|-----------|------|
| postgres | - | ✅ 仅容器网络 |
| redis | - | ✅ 仅容器网络 |
| backend | - | ✅ 仅容器网络 |
| frontend | - | ✅ 仅容器网络 |
| nginx | **80, 443** | ✅ **唯一对外暴露** |
| celery-exporter | - | ✅ 仅容器网络 |
| metabase | **127.0.0.1:8080** | ✅ **仅本地访问** |

**总计**: 2 个对外暴露端口（80/443）+ 1 个本地端口（127.0.0.1:8080）

## 🎯 安全性提升

- ✅ **端口暴露减少**: 从 7 个减少到 2 个（减少 71%）
- ✅ **数据库隔离**: PostgreSQL 和 Redis 完全隔离，公网无法访问
- ✅ **后端隔离**: Backend API 不直接暴露，只能通过 Nginx 访问
- ✅ **前端隔离**: Frontend 不直接暴露，只能通过 Nginx 访问
- ✅ **Metabase 安全**: 仅管理员可通过 SSH 隧道访问

## 🚀 部署命令

### 核心服务（推荐）

```bash
docker-compose --env-file .env \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.cloud.yml \
  -f docker-compose.prod.lockdown.yml \
  --profile production up -d
```

### 核心服务 + Metabase

```bash
docker-compose --env-file .env \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.cloud.yml \
  -f docker-compose.metabase.yml \
  -f docker-compose.prod.lockdown.yml \
  -f docker-compose.metabase.lockdown.yml \
  --profile production up -d
```

## ✅ 功能验证

### 服务间通信（不受影响）

- ✅ 后端 → 数据库: `postgres:5432`（容器网络）
- ✅ 后端 → Redis: `redis:6379`（容器网络）
- ✅ Nginx → 后端: `backend:8000`（容器网络）
- ✅ Nginx → 前端: `frontend:80`（容器网络）

### 外部访问

- ✅ 前端: `http://YOUR_SERVER_IP/`（通过 Nginx）
- ✅ 后端 API: `http://YOUR_SERVER_IP/api/health`（通过 Nginx）
- ✅ Metabase: `http://localhost:8080`（仅本地，需 SSH 隧道）

## 🔐 Metabase 访问方式

### SSH 隧道（推荐）

```bash
# 在本地电脑执行
ssh -L 8080:127.0.0.1:8080 deploy@YOUR_SERVER_IP

# 然后浏览器访问
http://localhost:8080
```

## ⚠️ 注意事项

1. **数据库管理工具**: 如需使用 pgAdmin，使用 SSH 隧道或临时开放端口
2. **Redis 管理工具**: 使用 SSH 隧道或在容器内使用 `redis-cli`
3. **监控工具**: Prometheus 应在同一 Docker 网络中，通过容器网络名访问

## 📝 回退方案

如需回退到原来的配置（所有端口都暴露）：

```bash
# 不使用 lockdown 配置文件
docker-compose --env-file .env \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.cloud.yml \
  --profile production up -d
```

## ✅ 总结

**配置状态**: ✅ **完成并验证通过**

**安全性**: ✅ **大幅提升**（端口暴露减少 71%）

**功能完整性**: ✅ **不受影响**（所有服务正常运行）

**部署就绪**: ✅ **是** - 可以安全部署到生产环境
