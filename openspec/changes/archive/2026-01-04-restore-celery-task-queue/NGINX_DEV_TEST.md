# Nginx 开发环境测试指南

> **状态**: ✅ 配置已完成  
> **创建时间**: 2026-01-03  
> **目的**: 在开发环境测试 Nginx 反向代理和限流功能，提前发现生产环境问题

## 📋 概述

本指南说明如何在开发环境启动和测试 Nginx 服务。

## 🚀 快速开始

### 前置条件

1. **后端服务运行在**: `http://localhost:8001`
2. **前端服务运行在**: `http://localhost:5173` (Vite 开发服务器)
3. **Docker 和 Docker Compose 已安装**

### 启动步骤

#### 1. 启动基础服务（如果未启动）

```bash
# 启动数据库和 Redis
docker-compose --profile dev up -d postgres redis

# 或启动完整开发环境（包括后端和前端容器）
docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev-full up -d
```

#### 2. 启动本地后端和前端（如果使用本地开发）

```bash
# 后端（新终端窗口）
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8001

# 前端（新终端窗口）
cd frontend
npm run dev
```

#### 3. 启动 Nginx（开发环境）

```bash
# 启动 Nginx 服务
docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev-nginx up -d

# 查看日志
docker-compose logs -f nginx
```

#### 4. 验证服务状态

```bash
# 查看所有服务状态
docker-compose ps

# 验证 Nginx 健康检查
curl http://localhost:8081/health
```

## 🧪 测试验证

### 1. 测试反向代理

#### 测试后端 API 代理

```bash
# 测试健康检查
curl http://localhost:8081/api/health

# 测试 API 文档
curl http://localhost:8081/api/docs

# 测试其他 API（需要认证）
curl http://localhost:8081/api/collection/accounts
```

**期望结果**:
- 返回后端 API 的响应
- 状态码为 200（或相应的状态码）

#### 测试前端代理

```bash
# 访问前端页面
curl http://localhost:8081/

# 或直接在浏览器访问
# http://localhost:8081
```

**期望结果**:
- 返回前端页面内容
- Vite HMR 正常工作（热重载）

### 2. 测试限流功能

#### 测试通用 API 限流

```bash
# 快速发送多个请求（超过限流阈值）
for i in {1..600}; do
  curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8081/api/health
  sleep 0.1
done
```

**期望结果**:
- 前 500 个请求返回 200
- 超过限流后返回 429 (Too Many Requests)

#### 测试数据同步 API 限流

```bash
# 快速发送多个数据同步请求
for i in {1..120}; do
  curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8081/api/data-sync/files
  sleep 0.1
done
```

**期望结果**:
- 前 100 个请求返回 200（或相应的状态码）
- 超过限流后返回 429

#### 测试认证 API 限流

```bash
# 快速发送多个登录请求
for i in {1..40}; do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8081/api/auth/login
  sleep 0.1
done
```

**期望结果**:
- 前 30 个请求返回相应状态码
- 超过限流后返回 429

### 3. 测试日志

```bash
# 查看访问日志
docker exec xihong_erp_nginx_dev tail -f /var/log/nginx/access.log

# 查看错误日志
docker exec xihong_erp_nginx_dev tail -f /var/log/nginx/error.log
```

**期望结果**:
- 访问日志包含请求详情（IP、时间、状态码等）
- 错误日志包含错误信息（如果有）

## 🔧 故障排除

### 问题1: 无法连接到后端服务

**症状**: Nginx 返回 502 Bad Gateway

**可能原因**:
1. 后端服务未启动
2. `host.docker.internal` 不可用（Linux 系统）

**解决方案**:

#### Linux 用户

在 `docker-compose.dev.yml` 中取消注释 `extra_hosts` 配置：

```yaml
nginx:
  extra_hosts:
    - "host.docker.internal:host-gateway"
```

然后重启 Nginx：

```bash
docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev-nginx up -d --force-recreate
```

#### 验证后端服务

```bash
# 检查后端是否运行
curl http://localhost:8001/health

# 检查端口是否监听
# Windows
netstat -ano | findstr :8001

# Linux/Mac
lsof -i:8001
```

### 问题2: 无法连接到前端服务

**症状**: Nginx 返回 502 Bad Gateway

**可能原因**:
1. 前端服务未启动
2. Vite 开发服务器端口不正确

**解决方案**:

```bash
# 检查前端是否运行
curl http://localhost:5173

# 检查 Vite 配置
# frontend/vite.config.js 中应配置 server.host = '0.0.0.0'
```

### 问题3: 限流不生效

**症状**: 发送大量请求后未返回 429

**可能原因**:
1. 限流配置未正确加载
2. 请求速度不够快

**解决方案**:

```bash
# 检查 Nginx 配置语法
docker exec xihong_erp_nginx_dev nginx -t

# 重新加载配置
docker exec xihong_erp_nginx_dev nginx -s reload

# 使用更快的请求速度测试
ab -n 1000 -c 10 http://localhost:8081/api/health
```

### 问题4: 端口冲突

**症状**: 启动失败，提示端口 8080 已被占用

**解决方案**:

```bash
# 修改 docker-compose.dev.yml 中的端口映射
ports:
  - "8082:80"  # 改为其他端口（当前使用 8081，避免与 Metabase 8080 冲突）

# 或停止占用端口的服务
# Windows
netstat -ano | findstr :8081
taskkill /PID <PID> /F

# Linux/Mac
lsof -i:8080
kill -9 <PID>
```

## 📊 配置说明

### 开发环境 vs 生产环境

| 特性 | 开发环境 | 生产环境 |
|------|---------|---------|
| 后端地址 | `localhost:8001` | `backend:8000` (Docker 网络) |
| 前端地址 | `localhost:5173` (Vite) | `frontend:80` (Docker 容器) |
| 端口 | 8081 | 80/443 |
| 限流规则 | 更宽松（便于测试） | 严格（防护） |
| 日志级别 | debug | warn |
| SSL | 无 | 有 |

### 限流规则对比

| API 类型 | 开发环境 | 生产环境 |
|---------|---------|---------|
| 通用 API | 500 次/分钟 | 200 次/分钟 |
| 数据同步 API | 100 次/分钟 | 30 次/分钟 |
| 认证 API | 30 次/分钟 | 10 次/分钟 |
| 并发连接 | 50 个/IP | 20 个/IP |

## 🎯 下一步

完成开发环境测试后：

1. ✅ 验证反向代理功能正常
2. ✅ 验证限流功能正常
3. ✅ 验证日志记录正常
4. ⏭️ 准备生产环境部署（使用 `nginx.prod.conf`）

## 📝 相关文件

- `nginx/nginx.dev.conf` - 开发环境 Nginx 配置
- `nginx/nginx.prod.conf` - 生产环境 Nginx 配置
- `docker-compose.dev.yml` - 开发环境 Docker Compose 配置

