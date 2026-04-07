# Docker 启动完整指南

## ✅ 已完成的工作

### 1. 数据库用户和数据库创建 ✅

- **用户**: `erp_dev`
- **数据库**: `xihong_erp_dev`
- **状态**: 已创建并验证

### 2. 数据库表初始化 ✅

- **表数量**: 98 张表
- **关键表**: `dim_users`, `dim_roles`, `fact_orders`, `catalog_files` 等
- **状态**: 所有表已成功创建

### 3. Docker Compose 服务配置 ✅

- **PostgreSQL**: 运行正常
- **Redis**: 运行正常（带密码认证）
- **Backend**: 运行正常，健康检查通过
- **Celery Worker**: 运行正常

### 4. 前端 API 配置修复 ✅

- **baseURL**: 已改为相对路径 `/api`
- **Vite 代理**: 已正确配置

## 📋 启动步骤

### 方式 1：使用统一启动脚本（推荐）

```bash
# 使用Docker Compose模式启动（推荐）
python run.py --use-docker
```

这个命令会：

1. 启动 Redis 和 PostgreSQL
2. 启动后端 API 服务（Docker 容器）
3. 启动 Celery Worker（Docker 容器）
4. 启动前端开发服务器（本地）
5. 自动打开浏览器

### 方式 2：手动启动 Docker Compose

```bash
# 启动所有服务
docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev-full up -d

# 查看日志
docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f

# 停止服务
docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev-full down
```

## 🔧 初始化数据库

### 创建数据库表

如果数据库表不存在，执行以下命令创建：

```bash
# 方式1：使用临时脚本（推荐，更健壮）
docker cp temp/init_tables_in_container.py xihong_erp_backend_dev:/tmp/init_tables.py
docker exec xihong_erp_backend_dev python /tmp/init_tables.py

# 方式2：使用init_db函数
docker exec xihong_erp_backend_dev python -c "from backend.models.database import init_db; init_db()"
```

### 创建管理员用户

```bash
# 复制脚本到容器
docker cp scripts/create_admin_user.py xihong_erp_backend_dev:/tmp/create_admin_user.py

# 执行脚本
docker exec xihong_erp_backend_dev python /tmp/create_admin_user.py
```

**默认管理员账号**：

- **用户名**: `xihong`
- **密码**: `~!Qq1`1``
- **邮箱**: `xihong@xihong.com`

## 🔍 验证服务状态

### 检查容器状态

```bash
# 查看所有容器状态
docker ps --filter "name=xihong_erp"

# 查看特定容器日志
docker logs xihong_erp_backend_dev
docker logs xihong_erp_celery_worker_dev
docker logs xihong_erp_postgres
docker logs xihong_erp_redis_dev
```

### 检查服务健康状态

```bash
# 后端健康检查
curl http://localhost:8001/health

# 前端访问
curl http://localhost:5173
```

### 检查数据库连接

#### 方式1：在容器内连接（推荐，用于调试）

```bash
# 连接PostgreSQL（容器内）
docker exec -it xihong_erp_postgres psql -U erp_dev -d xihong_erp_dev

# 查看表数量
docker exec xihong_erp_postgres psql -U erp_dev -d xihong_erp_dev -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';"

# 查看用户
docker exec xihong_erp_postgres psql -U erp_dev -d xihong_erp_dev -c "SELECT user_id, username, email, status, is_active FROM dim_users;"
```

#### 方式2：从宿主机连接（用于外部工具，如pgAdmin、Metabase）

**端口配置说明**：

- **开发环境**: PostgreSQL 映射到宿主机端口 `15432`（避免与本地 PostgreSQL 冲突）
- **容器内部**: 容器内仍使用标准端口 `5432`
- **容器间通信**: 使用服务名 `postgres:5432`

```bash
# 从宿主机连接（使用15432端口）
psql -h localhost -p 15432 -U erp_dev -d xihong_erp_dev

# 或者使用连接字符串
psql "postgresql://erp_dev:dev_pass_2025@localhost:15432/xihong_erp_dev"
```

**为什么使用15432端口？**

开发环境中，如果您的本地机器上已经运行了 PostgreSQL（通常在5432端口），使用15432端口可以：
- ✅ 避免端口冲突
- ✅ 明确区分容器化数据库和本地数据库
- ✅ 允许同时运行本地和容器化PostgreSQL

## 🚨 常见问题排查

### 1. 后端服务无法启动

**症状**: 容器状态为 `unhealthy` 或不断重启

**检查**:

```bash
# 查看容器日志
docker logs xihong_erp_backend_dev

# 检查数据库连接
docker exec xihong_erp_backend_dev env | grep DATABASE_URL
```

**解决方案**:

- 确保 PostgreSQL 容器运行正常
- 检查数据库用户是否存在（参考上面的数据库用户创建步骤）
- 检查环境变量配置（`.env`文件）

### 2. 前端无法连接后端

**症状**: 前端显示"Network Error"

**检查**:

```bash
# 检查后端是否运行
curl http://localhost:8001/health

# 检查前端API配置
cat frontend/src/api/index.js | grep baseURL
```

**解决方案**:

- 确保后端服务正常运行（健康检查返回 200）
- 检查前端 API baseURL 配置（应该使用相对路径 `/api`）
- 检查 Vite 代理配置（`frontend/vite.config.js`）

### 3. Celery Worker 无法启动

**症状**: 数据同步任务一直处于"等待"状态

**检查**:

```bash
# 查看Celery Worker日志
docker logs xihong_erp_celery_worker_dev

# 检查Redis连接
docker exec xihong_erp_celery_worker_dev env | grep REDIS
```

**解决方案**:

- 确保 Redis 容器运行正常
- 检查 Redis 密码配置（`.env`文件中的`REDIS_PASSWORD`）
- 检查`REDIS_URL`环境变量

### 4. 数据库表不存在

**症状**: 登录或查询时返回 500 错误，日志显示"relation does not exist"

**解决方案**:
参考上面的"创建数据库表"步骤

### 5. 登录失败

**症状**: 前端显示登录失败

**检查**:

```bash
# 检查用户是否存在
docker exec xihong_erp_postgres psql -U erp_dev -d xihong_erp_dev -c "SELECT user_id, username, email, status, is_active FROM dim_users;"
```

**解决方案**:

- 如果用户不存在，参考上面的"创建管理员用户"步骤
- 如果用户存在但状态为`pending`，需要使用超级用户账号登录并审批

## 📝 环境变量配置

确保 `.env` 文件包含以下配置：

```env
# PostgreSQL
POSTGRES_USER=erp_dev
POSTGRES_PASSWORD=dev_pass_2025
POSTGRES_DB=xihong_erp_dev
# ⭐ Docker容器内部使用服务名 postgres:5432（容器间通信）
DATABASE_URL=postgresql://erp_dev:dev_pass_2025@postgres:5432/xihong_erp_dev
# ⭐ 本地开发环境（从宿主机连接）使用 localhost:15432
# DATABASE_URL=postgresql://erp_dev:dev_pass_2025@localhost:15432/xihong_erp_dev

# Redis
REDIS_PASSWORD=~!Qq11
REDIS_URL=redis://:~!Qq11@redis:6379/0

# Celery
CELERY_BROKER_URL=redis://:~!Qq11@redis:6379/0
CELERY_RESULT_BACKEND=redis://:~!Qq11@redis:6379/0
```

**重要说明**：

- **容器内连接**（Docker服务间通信）：使用 `postgres:5432`（服务名）
- **宿主机连接**（本地工具，如pgAdmin、Metabase）：使用 `localhost:15432`（映射端口）
- **为什么使用15432端口？** 避免与本地PostgreSQL（通常运行在5432端口）冲突

## ✅ 管理员用户已创建

**默认管理员账号**:

- **用户名**: `xihong`
- **密码**: `~!Qq1`1``
- **邮箱**: `xihong@xihong.com`
- **角色**: 管理员（admin）
- **状态**: 已激活（active）
- **权限**: 超级用户（is_superuser=True）

**验证用户**:

```bash
docker exec xihong_erp_postgres psql -U erp_dev -d xihong_erp_dev -c "SELECT user_id, username, email, status, is_active, is_superuser FROM dim_users;"
```

**重新创建管理员用户**（如果需要）:

```bash
docker exec -e PYTHONPATH=/app xihong_erp_backend_dev python /tmp/create_admin_user.py
```

## 🎯 下一步

1. ✅ **管理员用户已创建** - 可以使用上述账号登录
2. **访问前端**: http://localhost:5173
3. **访问 API 文档**: http://localhost:8001/api/docs
4. **测试登录功能** - 使用 `xihong` / `~!Qq1`1`` 登录

## 📚 相关文档

- [Docker 启动指南](docs/DOCKER_STARTUP_GUIDE.md)
- [诊断总结](docs/DIAGNOSIS_SUMMARY.md)
- [开发规范](.cursorrules)
