# 完整系统启动指南

**版本**: v4.6.0 + Superset  
**最后更新**: 2025-11-23

## 🎯 快速启动（推荐）

### 一键启动所有服务

```bash
# 方式1: 使用便捷脚本（推荐）
start_system_with_redis.bat  # Windows
# 然后启动Superset
python scripts/start_superset.py start

# 方式2: 使用run.py（集成Superset）
python run.py --with-superset
```

## 📋 服务清单

### 核心服务（必需）

1. **PostgreSQL数据库**
   - 端口: 5432
   - 容器: `xihong_erp_postgres`
   - 启动: `docker-compose up -d postgres`

2. **后端API服务**
   - 端口: 8001
   - 启动: `python run.py --backend-only`
   - 文档: http://localhost:8001/api/docs

3. **前端界面**
   - 端口: 5173
   - 启动: `python run.py --frontend-only`
   - 访问: http://localhost:5173

### BI服务（可选但推荐）

4. **Superset BI平台**
   - 端口: 8088
   - 启动: `python scripts/start_superset.py start`
   - 访问: http://localhost:8088
   - 账号: admin / admin

5. **Redis缓存**（可选，性能优化）
   - 端口: 6379
   - 启动: `docker run -d -p 6379:6379 --name xihong_erp_redis redis:alpine`

## 🚀 启动步骤详解

### 步骤1: 启动PostgreSQL

```bash
# 检查PostgreSQL状态
docker ps | grep xihong_erp_postgres

# 如果未运行，启动PostgreSQL
docker-compose up -d postgres

# 验证
docker ps | grep postgres
```

### 步骤2: 启动ERP系统

```bash
# 完整启动（后端+前端）
python run.py

# 或分别启动
python run.py --backend-only  # 仅后端
python run.py --frontend-only  # 仅前端
```

### 步骤3: 启动Superset（可选）

```bash
# 使用便捷脚本
python scripts/start_superset.py start

# 或使用Docker Compose
docker-compose -f docker-compose.superset.yml up -d
```

### 步骤4: 验证所有服务

```bash
# 检查所有服务状态
docker ps

# 应该看到：
# - xihong_erp_postgres (PostgreSQL)
# - superset (Superset主服务)
# - superset_redis (Redis缓存)
# - superset_worker (异步任务)
# - superset_beat (定时任务)

# 检查端口占用
netstat -ano | findstr "5432 8001 5173 8088 6379"
```

## 🌐 访问地址汇总

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端界面 | http://localhost:5173 | Vue.js主界面 |
| 后端API | http://localhost:8001 | FastAPI服务 |
| API文档 | http://localhost:8001/api/docs | Swagger文档 |
| Superset | http://localhost:8088 | BI平台 |
| PostgreSQL | localhost:5432 | 数据库（需客户端） |

## 📊 启动模式

### 模式1: 最小启动（开发调试）

```bash
# 仅启动PostgreSQL和ERP系统
docker-compose up -d postgres
python run.py
```

**特点**:
- ✅ 启动快速
- ✅ 功能完整
- ❌ 无BI功能
- ❌ 无缓存加速

### 模式2: 标准启动（日常开发）

```bash
# PostgreSQL + ERP系统 + Superset
docker-compose up -d postgres
python run.py
python scripts/start_superset.py start
```

**特点**:
- ✅ 功能完整
- ✅ 包含BI功能
- ✅ 适合数据分析

### 模式3: 完整启动（生产环境）

```bash
# 所有服务 + Redis缓存
docker-compose up -d postgres
docker run -d -p 6379:6379 --name xihong_erp_redis redis:alpine
python run.py
python scripts/start_superset.py start
```

**特点**:
- ✅ 性能最优（Redis缓存）
- ✅ 功能完整
- ✅ 适合生产环境

## 🔧 启动脚本说明

### run.py（主启动脚本）

```bash
# 基本用法
python run.py                    # 启动后端+前端
python run.py --backend-only     # 仅后端
python run.py --frontend-only     # 仅前端
python run.py --with-superset     # 同时启动Superset
python run.py --no-browser        # 不自动打开浏览器
```

### start_superset.py（Superset管理）

```bash
python scripts/start_superset.py start   # 启动
python scripts/start_superset.py stop    # 停止
python scripts/start_superset.py status  # 状态
```

## ⚠️ 常见问题

### 问题1: 端口冲突

**症状**: 服务启动失败，提示端口被占用

**解决**:
```bash
# Windows
netstat -ano | findstr <端口号>
taskkill /PID <PID> /F

# Linux/Mac
lsof -i :<端口号>
kill -9 <PID>
```

### 问题2: PostgreSQL连接失败

**检查**:
1. PostgreSQL容器是否运行: `docker ps | grep postgres`
2. 数据库连接配置: 检查`.env`文件
3. 网络连接: 确保服务在同一网络

### 问题3: Superset无法访问

**检查**:
1. 容器状态: `docker ps | grep superset`
2. 等待时间: Superset需要30-60秒完全启动
3. 日志查看: `docker-compose -f docker-compose.superset.yml logs superset`

## 📚 相关文档

- **系统启动指南**: `docs/SYSTEM_STARTUP_GUIDE.md`
- **Superset启动**: `docs/SUPERSET_STARTUP_GUIDE.md`
- **Superset部署**: `docs/SUPERSET_DEPLOYMENT_COMPLETE.md`
- **快速设置**: `docs/QUICK_SETUP_STEPS.md`

---

**最后更新**: 2025-11-23

