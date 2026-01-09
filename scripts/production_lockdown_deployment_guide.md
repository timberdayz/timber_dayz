# 生产环境最小端口暴露部署指南

**更新时间**: 2025-01-09  
**目的**: 最小化端口暴露，只对外暴露 Nginx 的 80/443，提高安全性

## 🎯 安全原则

### 对外暴露的端口（仅 2 个）
- ✅ **80** (HTTP) - Nginx 反向代理
- ✅ **443** (HTTPS) - Nginx 反向代理（SSL）

### 不对外暴露的服务（仅在 Docker 内网可访问）
- ❌ **PostgreSQL** (5432) - 仅容器网络 `postgres:5432` 可访问
- ❌ **Redis** (6379) - 仅容器网络 `redis:6379` 可访问
- ❌ **Backend** (8000) - 仅容器网络 `backend:8000` 可访问
- ❌ **Frontend** (80) - 仅容器网络 `frontend:80` 可访问
- ❌ **Celery Exporter** (9540) - 仅容器网络 `celery-exporter:9540` 可访问
- ❌ **Metabase** (3000) - 绑定到 `127.0.0.1:8080`，仅本地访问

## 📁 配置文件说明

### 1. `docker-compose.prod.lockdown.yml`
- 移除所有非 Nginx 服务的宿主机端口映射
- 服务仍可通过容器网络名访问（如 `backend:8000`）

### 2. `docker-compose.metabase.lockdown.yml`
- Metabase 绑定到 `127.0.0.1:8080`，不对外暴露
- 管理员可通过 SSH 隧道访问

## 🚀 部署命令

### 方案1：只部署核心服务（最小化部署）

```bash
docker-compose --env-file .env \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.cloud.yml \
  -f docker-compose.prod.lockdown.yml \
  --profile production up -d
```

**会启动的服务** (8个):
- postgres（无宿主机端口）
- redis（无宿主机端口）
- backend（无宿主机端口）
- frontend（无宿主机端口）
- nginx（**80/443** 对外暴露）
- celery-worker（无宿主机端口）
- celery-beat（无宿主机端口）
- celery-exporter（无宿主机端口）

### 方案2：核心服务 + Metabase（推荐生产环境）

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

**会启动的服务** (9个):
- 核心服务 (8个)
- metabase（**127.0.0.1:8080**，仅本地访问）

## 🔒 安全性验证

### 验证端口映射

```bash
# 检查所有服务的端口映射
docker-compose -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.prod.lockdown.yml \
  --profile production config | grep -A 5 "ports:"

# 应该只看到 nginx 的 80 和 443
```

### 验证服务间通信

所有服务仍可通过容器网络名访问：
- 后端 → 数据库: `postgres:5432` ✅
- 后端 → Redis: `redis:6379` ✅
- Nginx → 后端: `backend:8000` ✅
- Nginx → 前端: `frontend:80` ✅

## 🔐 Metabase 安全访问

### 方式1：SSH 隧道（推荐）

```bash
# 在本地电脑执行
ssh -L 8080:127.0.0.1:8080 deploy@YOUR_SERVER_IP

# 然后浏览器访问
http://localhost:8080
```

### 方式2：临时开放（不推荐）

如果需要临时开放 Metabase 到公网：

```bash
# 修改 docker-compose.metabase.lockdown.yml
# 将 127.0.0.1:8080:3000 改为 8080:3000
# 然后重启服务
docker-compose -f docker-compose.metabase.yml restart metabase
```

**⚠️ 警告**: 临时开放后，记得改回 `127.0.0.1:8080:3000`

## ✅ 功能验证

### 1. 验证 Nginx 反向代理

```bash
# 测试前端
curl http://YOUR_SERVER_IP/

# 测试后端 API
curl http://YOUR_SERVER_IP/api/health
```

### 2. 验证服务间通信

```bash
# 在后端容器内测试数据库连接
docker exec xihong_erp_backend python -c "from sqlalchemy import create_engine; import os; engine = create_engine(os.getenv('DATABASE_URL')); conn = engine.connect(); conn.close(); print('OK')"

# 在后端容器内测试 Redis 连接
docker exec xihong_erp_backend python -c "import redis; r = redis.from_url(os.getenv('REDIS_URL')); r.ping(); print('OK')"
```

### 3. 验证端口未暴露

```bash
# 检查宿主机端口监听（应该只看到 80 和 443）
netstat -tlnp | grep LISTEN

# 或使用 ss
ss -tlnp | grep LISTEN
```

## 📊 端口映射对比

### 修改前（不安全）
| 服务 | 宿主机端口 | 容器端口 | 状态 |
|------|-----------|---------|------|
| postgres | 5432 | 5432 | ❌ 对外暴露 |
| redis | 6379 | 6379 | ❌ 对外暴露 |
| backend | 8000 | 8000 | ❌ 对外暴露 |
| frontend | 3000 | 80 | ❌ 对外暴露 |
| nginx | 80, 443 | 80, 443 | ✅ 需要暴露 |
| celery-exporter | 9808 | 9540 | ❌ 对外暴露 |
| metabase | 8080 | 3000 | ❌ 对外暴露 |

### 修改后（安全）
| 服务 | 宿主机端口 | 容器端口 | 状态 |
|------|-----------|---------|------|
| postgres | - | 5432 | ✅ 仅容器网络 |
| redis | - | 6379 | ✅ 仅容器网络 |
| backend | - | 8000 | ✅ 仅容器网络 |
| frontend | - | 80 | ✅ 仅容器网络 |
| nginx | **80, 443** | 80, 443 | ✅ **唯一对外暴露** |
| celery-exporter | - | 9540 | ✅ 仅容器网络 |
| metabase | **127.0.0.1:8080** | 3000 | ✅ **仅本地访问** |

## ⚠️ 注意事项

### 1. 数据库管理工具

如果需要使用 pgAdmin 或其他数据库管理工具：

**选项1**: 使用 SSH 隧道
```bash
ssh -L 5432:127.0.0.1:5432 deploy@YOUR_SERVER_IP
# 然后连接 localhost:5432
```

**选项2**: 临时开放端口（不推荐）
- 修改 `docker-compose.prod.lockdown.yml`，临时添加 `postgres` 的端口映射
- 使用后立即移除

### 2. Redis 管理工具

如果需要使用 Redis 管理工具：

**选项1**: 使用 SSH 隧道
```bash
ssh -L 6379:127.0.0.1:6379 deploy@YOUR_SERVER_IP
# 然后连接 localhost:6379
```

**选项2**: 在容器内使用 redis-cli
```bash
docker exec -it xihong_erp_redis redis-cli -a YOUR_REDIS_PASSWORD
```

### 3. 监控工具

如果使用 Prometheus 等监控工具：
- Prometheus 应该在同一个 Docker 网络中
- 通过容器网络名访问（如 `celery-exporter:9540`）
- 不需要宿主机端口映射

## 🔄 回退方案

如果需要回退到原来的配置（所有端口都暴露）：

```bash
# 不使用 lockdown 配置文件即可
docker-compose --env-file .env \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.cloud.yml \
  --profile production up -d
```

## ✅ 总结

**安全性提升**:
- ✅ 从 7 个对外暴露端口减少到 2 个（80/443）
- ✅ 数据库和缓存服务完全隔离
- ✅ Metabase 仅管理员可访问
- ✅ 服务间通信不受影响（通过容器网络）

**功能完整性**:
- ✅ 所有服务正常运行
- ✅ Nginx 反向代理正常工作
- ✅ 前端和后端可正常访问
- ✅ 数据库和 Redis 连接正常
