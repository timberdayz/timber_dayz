# Docker Compose 启动指南

## 📋 概述

本文档说明如何使用 Docker Compose 模式启动西虹ERP系统（**生产就绪模式**）。

### ⭐ 为什么使用 Docker Compose 模式？

1. **与生产环境一致**：开发环境和生产环境使用相同的 Docker 配置
2. **服务隔离**：所有服务运行在独立容器中，避免本地环境干扰
3. **依赖管理**：自动管理服务依赖和启动顺序
4. **健康检查**：自动验证服务是否真正可用（容器运行 ≠ 服务就绪）
5. **一键部署**：支持在 Linux 服务器上直接部署

---

## 🚀 快速启动

### 方式1：使用启动脚本（推荐）

```bash
# Docker Compose 模式（推荐，与生产环境一致）
python run.py --use-docker
```

这将自动：
1. ✅ 启动 Redis 和 PostgreSQL 容器
2. ✅ 启动后端 API 容器（带健康检查）
3. ✅ 启动 Celery Worker 容器
4. ✅ 等待所有服务健康检查通过
5. ✅ 启动前端服务（本地，便于开发调试）

### 方式2：直接使用 Docker Compose

```bash
# 启动所有服务
docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev-full up -d

# 查看服务状态
docker-compose -f docker-compose.yml -f docker-compose.dev.yml ps

# 查看日志
docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f
```

---

## 🏗️ 架构说明

### 服务架构

```
┌─────────────────────────────────────────────┐
│          Docker Compose 网络                │
│         (erp_network)                       │
├─────────────────────────────────────────────┤
│                                             │
│  ┌──────────────┐    ┌──────────────┐     │
│  │  PostgreSQL  │    │    Redis     │     │
│  │   (5432)     │    │   (6379)     │     │
│  └──────────────┘    └──────────────┘     │
│         ▲                   ▲               │
│         │                   │               │
│  ┌──────────────┐    ┌──────────────┐     │
│  │   Backend    │───▶│    Celery    │     │
│  │   (8001)     │    │   Worker     │     │
│  └──────────────┘    └──────────────┘     │
│         │                                   │
└─────────┼───────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────┐
│         本地主机 (Host)                     │
│                                             │
│  ┌──────────────┐                          │
│  │   Frontend   │─────▶ http://localhost:  │
│  │   (5173)     │      8001/api            │
│  └──────────────┘                          │
└─────────────────────────────────────────────┘
```

### 端口映射

| 服务 | 容器端口 | 主机端口 | 访问地址 |
|------|---------|---------|---------|
| 后端 API | 8000 | 8001 | http://localhost:8001 |
| 前端 | 5173 | 5173 | http://localhost:5173 |
| PostgreSQL | 5432 | 5432 | localhost:5432 |
| Redis | 6379 | 6379 | localhost:6379 |
| Metabase | 8080 | 8080 | http://localhost:8080 |

---

## ⚙️ 健康检查机制

### 后端服务健康检查

系统会**自动等待后端服务健康检查通过**，确保服务真正可用：

```yaml
healthcheck:
  test: ["CMD-SHELL", "curl -f http://localhost:8000/healthz/ready || exit 1"]
  interval: 10s      # 每10秒检查一次
  timeout: 5s        # 超时时间5秒
  retries: 5         # 失败重试5次
  start_period: 40s  # 给服务40秒启动时间
```

### 启动流程

1. **容器启动** → `docker-compose up -d`
2. **等待容器运行** → 验证容器进程存在
3. **等待健康检查通过** → 测试 `/health` 端点（最多等待5分钟）
4. **服务就绪** → 可以接受请求

---

## 🔍 诊断和调试

### 检查服务状态

```bash
# 查看所有容器状态
docker ps -a

# 查看后端容器状态
docker ps -a | grep backend

# 查看后端容器日志
docker logs xihong_erp_backend_dev -f

# 测试后端健康检查
curl http://localhost:8001/healthz/ready
# 或在 PowerShell 中：
Invoke-WebRequest -Uri http://localhost:8001/healthz/ready
```

### 常见问题

#### 1. 后端容器启动但无法访问

**症状**：容器显示 "running"，但前端报 "Network Error"

**诊断步骤**：
```bash
# 1. 检查容器日志
docker logs xihong_erp_backend_dev --tail 50

# 2. 测试健康检查端点
curl http://localhost:8001/healthz/ready

# 3. 检查容器内进程
docker exec xihong_erp_backend_dev ps aux | grep uvicorn

# 4. 检查数据库连接
docker exec xihong_erp_backend_dev env | grep DATABASE_URL
```

**可能原因**：
- 数据库连接失败
- 端口被占用
- 环境变量配置错误
- 依赖未安装

#### 2. 首次构建超时

**症状**：构建时间超过5分钟

**解决方案**：
```bash
# 手动构建镜像
docker-compose -f docker-compose.yml -f docker-compose.dev.yml build backend

# 然后启动
docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev-full up -d backend
```

#### 3. Redis 连接失败

**症状**：Celery Worker 无法连接 Redis

**检查**：
```bash
# 检查 Redis 容器
docker ps | grep redis

# 测试 Redis 连接
docker exec xihong_erp_redis_dev redis-cli -a ~!Qq11 ping
```

**修复**：确保 `.env` 文件中配置了正确的 `REDIS_PASSWORD`

---

## 🛠️ 常用命令

### 启动和停止

```bash
# 启动所有服务
python run.py --use-docker

# 停止所有服务
docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev-full down

# 停止并删除数据卷（⚠️ 警告：会删除数据）
docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev-full down -v
```

### 查看日志

```bash
# 查看所有服务日志
docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f

# 查看后端日志
docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f backend

# 查看 Celery Worker 日志
docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f celery-worker

# 查看后端容器实时日志
docker logs xihong_erp_backend_dev -f
```

### 重启服务

```bash
# 重启后端服务
docker-compose -f docker-compose.yml -f docker-compose.dev.yml restart backend

# 重启 Celery Worker
docker-compose -f docker-compose.yml -f docker-compose.dev.yml restart celery-worker

# 重建并重启后端
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build backend
```

### 进入容器调试

```bash
# 进入后端容器
docker exec -it xihong_erp_backend_dev /bin/bash

# 进入 PostgreSQL 容器
docker exec -it xihong_erp_postgres /bin/bash

# 进入 Redis 容器
docker exec -it xihong_erp_redis_dev /bin/sh
```

---

## 📝 环境变量配置

### 必需的环境变量

确保 `.env` 文件中配置了以下变量：

```env
# 数据库配置
DATABASE_URL=postgresql://erp_dev:dev_pass_2025@postgres:5432/xihong_erp_dev
POSTGRES_USER=erp_dev
POSTGRES_PASSWORD=dev_pass_2025
POSTGRES_DB=xihong_erp_dev

# Redis 配置
REDIS_URL=redis://:~!Qq11@localhost:6379/0
REDIS_PASSWORD=~!Qq11

# Celery 配置
CELERY_BROKER_URL=redis://:~!Qq11@redis:6379/0
CELERY_RESULT_BACKEND=redis://:~!Qq11@redis:6379/0
```

### 端口配置（可选）

```env
BACKEND_PORT=8001
FRONTEND_PORT=5173
REDIS_PORT=6379
POSTGRES_PORT=5432
```

---

## 🎯 最佳实践

### 1. 开发环境

- ✅ 使用 `python run.py --use-docker` 一键启动
- ✅ 前端在本地运行（便于调试）
- ✅ 后端、Redis、PostgreSQL 在容器中运行

### 2. 生产环境

- ✅ 所有服务都在容器中运行
- ✅ 使用 `docker-compose.prod.yml` 配置
- ✅ 启用资源限制和健康检查
- ✅ 配置日志轮转和监控

### 3. 调试技巧

- ✅ 使用 `docker logs -f` 实时查看日志
- ✅ 使用 `docker exec -it` 进入容器调试
- ✅ 使用健康检查端点验证服务状态
- ✅ 定期检查容器资源使用情况

---

## 📚 相关文档

- [系统架构文档](docs/architecture/FINAL_ARCHITECTURE_STATUS.md)
- [部署指南](docs/deployment/DEPLOYMENT_GUIDE.md)
- [开发规范](docs/DEVELOPMENT_RULES/)

---

## ⚠️ 注意事项

1. **首次启动需要时间**：首次构建 Docker 镜像需要几分钟，请耐心等待
2. **健康检查等待**：系统会自动等待后端服务健康检查通过，最多等待5分钟
3. **端口冲突**：确保端口 8001、5173、5432、6379 未被占用
4. **数据持久化**：数据存储在 Docker 数据卷中，删除容器不会删除数据
5. **Windows 开发**：Windows 上使用 Docker Desktop，确保已启用 WSL2

---

## 🆘 获取帮助

如果遇到问题：

1. 查看本文档的"诊断和调试"章节
2. 查看容器日志：`docker logs <container_name> -f`
3. 检查健康检查端点：`curl http://localhost:8001/healthz/ready`
4. 查看项目文档：`docs/` 目录

---

**最后更新**：2025-01-XX  
**版本**：v4.19.6

