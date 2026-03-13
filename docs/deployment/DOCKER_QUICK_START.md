# 🚀 西虹ERP系统 - Docker快速启动指南

> **版本**: v4.1.0  
> **更新时间**: 2025-10-23  
> **适用场景**: 开发环境 + 生产环境

---

## 📋 目录

1. [开发环境快速启动](#开发环境快速启动)
2. [生产环境部署](#生产环境部署)
3. [日常开发工作流](#日常开发工作流)
4. [24小时生产运行](#24小时生产运行)
5. [常见问题解决](#常见问题解决)

---

## 🔧 开发环境快速启动

### 前置要求
- ✅ Docker Desktop 已安装并运行
- ✅ Git 已安装
- ✅ Python 3.11+ 已安装
- ✅ Node.js 24+ 已安装

### 一键启动（推荐）

#### Windows
```bash
# 方式1：使用根目录快捷脚本（推荐）
start-docker-dev.bat

# 方式2：使用Docker脚本目录
docker\scripts\start-dev.bat
```

#### Linux/Mac
```bash
./docker/scripts/start-dev.sh
```

### 启动后访问

启动成功后，您可以访问：

- **数据库管理**: http://localhost:5051 (pgAdmin)
  - 邮箱: `admin@xihongerp.com`
  - 密码: `admin123`
  
- **PostgreSQL数据库**:
  - 主机: `localhost`
  - 端口: `5432`
  - 数据库: `xihong_erp`
  - 用户: `erp_user`
  - 密码: `erp_pass_2025`

### 验证启动状态

```bash
# 检查容器运行状态
docker-compose ps

# 应该看到2个容器运行：
# - postgres (健康)
# - pgadmin (健康)
```

---

## 🎯 日常开发工作流

### 推荐的开发模式：混合模式

**Docker运行**: PostgreSQL数据库  
**本地运行**: 后端API + 前端界面

#### 为什么推荐混合模式？

✅ **优点**:
- 数据库环境一致，避免安装PostgreSQL的复杂性
- 代码热重载快速，修改即生效
- 调试方便，可以直接在IDE中断点调试
- 资源占用低

❌ **纯Docker模式问题**:
- 代码修改需要重新构建镜像
- 调试不方便
- 重启速度慢

### 步骤1: 启动数据库（Docker）

```bash
# Windows
start-docker-dev.bat

# Linux/Mac
./docker/scripts/start-dev.sh
```

### 步骤2: 启动后端API（本地）

```bash
# 进入后端目录
cd backend

# 安装依赖（首次）
pip install -r requirements.txt

# 启动后端服务
python main.py

# 或使用uvicorn（推荐）
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**访问**: http://localhost:8000/docs (API文档)

### 步骤3: 启动前端（本地）

```bash
# 进入前端目录
cd frontend

# 安装依赖（首次）
npm install

# 启动开发服务器
npm run dev
```

**访问**: http://localhost:5173 (前端界面)

### 步骤4: 日常开发

```bash
# 后端开发
cd backend
# 修改代码 → 自动重载（--reload模式）

# 前端开发
cd frontend
# 修改代码 → 自动热重载（Vite HMR）

# 数据库管理
# 访问 http://localhost:5051 使用pgAdmin
```

---

## 🏭 生产环境部署

### 方式1: 完全Docker化部署（推荐生产环境）

#### 启动所有服务

```bash
# Windows
start-docker-prod.bat

# Linux/Mac
./docker/scripts/start-prod.sh
```

#### 包含的服务

- **PostgreSQL**: 数据库（端口5432）
- **pgAdmin**: 数据库管理（端口5051）
- **FastAPI**: 后端API（端口8000）
- **Vue.js**: 前端界面（端口80）

#### 访问地址

- 前端界面: http://localhost
- 后端API: http://localhost:8000
- 数据库管理: http://localhost:5051

### 方式2: 云服务器部署

#### 前置准备

```bash
# 1. SSH连接到服务器
ssh user@your-server-ip

# 2. 安装Docker和Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 3. 克隆代码
git clone https://github.com/your-repo/xihong_erp.git
cd xihong_erp
```

#### 配置环境变量

```bash
# 复制生产环境配置
cp env.production.example .env

# 编辑配置（重要！）
nano .env

# 修改以下内容：
# - SECRET_KEY（必须修改！）
# - POSTGRES_PASSWORD（必须修改！）
# - 其他安全配置
```

#### 启动服务

```bash
# 构建并启动
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 查看日志
docker-compose logs -f

# 检查状态
docker-compose ps
```

---

## ⚙️ 24小时生产运行

### 配置自动重启

已在`docker-compose.prod.yml`中配置：

```yaml
restart: unless-stopped  # 容器异常退出时自动重启
```

### 数据持久化

数据会自动持久化到Docker卷：

```bash
# 查看数据卷
docker volume ls | grep xihong

# 数据卷位置
# - postgres_data: 数据库数据
# - pgadmin_data: pgAdmin配置
```

### 日志管理

```bash
# 查看实时日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f postgres
docker-compose logs -f backend

# 清理旧日志（可选）
docker-compose logs --tail=1000 > logs_backup.txt
```

### 健康检查

```bash
# 使用健康检查脚本
docker/scripts/health-check.sh

# 手动检查
curl http://localhost:8000/health
```

### 监控和告警（推荐）

#### 方式1: 使用Docker内置健康检查

```bash
# 查看容器健康状态
docker ps --format "table {{.Names}}\t{{.Status}}"
```

#### 方式2: 使用监控工具（可选）

- **Portainer**: Docker容器可视化管理
- **Grafana + Prometheus**: 专业监控
- **Uptime Kuma**: 简单的服务监控

### 定期维护

```bash
# 每周执行一次（建议设置cron）

# 1. 清理未使用的镜像
docker system prune -a --volumes -f

# 2. 备份数据库
docker-compose exec -T postgres pg_dump -U erp_user xihong_erp > backup_$(date +%Y%m%d).sql

# 3. 检查磁盘空间
df -h

# 4. 更新系统
docker-compose pull
docker-compose up -d
```

---

## 🚨 常见问题解决

### 问题1: 端口冲突

**症状**: 启动时提示端口已被占用

**解决方案**:

```bash
# 检查5432端口占用
netstat -ano | findstr "5432"

# 停止本地PostgreSQL服务
stop-local-postgres.bat

# 或修改端口（不推荐）
# 编辑 docker-compose.yml，修改端口映射
```

### 问题2: Docker镜像拉取失败

**症状**: `TLS handshake timeout` 或下载速度慢

**解决方案**:

```bash
# 使用镜像加速脚本
fix-docker-mirror.bat

# 或手动配置Docker镜像源
# Docker Desktop → Settings → Docker Engine
# 添加：
{
  "registry-mirrors": [
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com"
  ]
}
```

### 问题3: 容器启动失败

**解决方案**:

```bash
# 查看详细错误日志
docker-compose logs postgres
docker-compose logs backend

# 重新构建
docker-compose down
docker-compose up -d --build --force-recreate

# 清理后重启
docker-compose down -v  # 警告：会删除数据！
docker-compose up -d
```

### 问题4: 数据库连接失败

**检查步骤**:

```bash
# 1. 检查容器运行
docker-compose ps

# 2. 测试数据库连接
docker-compose exec postgres psql -U erp_user -d xihong_erp -c "SELECT 1;"

# 3. 检查环境变量
cat .env | grep POSTGRES

# 4. 查看数据库日志
docker-compose logs postgres
```

### 问题5: 前端无法连接后端

**解决方案**:

```bash
# 检查后端API是否启动
curl http://localhost:8000/health

# 检查前端环境变量
cat frontend/.env
# 确保 VITE_API_URL=http://localhost:8000

# 重启前端
cd frontend
npm run dev
```

---

## 📚 额外资源

### 文档链接

- [完整Docker部署文档](DOCKER_DEPLOYMENT.md)
- [Docker使用示例](DOCKER_USAGE_EXAMPLES.md)
- [部署检查清单](DOCKER_CHECKLIST.md)

### 常用命令速查

```bash
# 启动服务
docker-compose up -d                    # 后台启动
docker-compose up -d --build           # 重新构建并启动

# 停止服务
docker-compose stop                     # 停止（保留容器）
docker-compose down                     # 停止并删除容器
docker-compose down -v                  # 停止并删除数据卷（危险！）

# 查看状态
docker-compose ps                       # 容器状态
docker-compose logs -f                  # 实时日志
docker-compose logs -f postgres         # 特定服务日志

# 执行命令
docker-compose exec postgres psql -U erp_user -d xihong_erp
docker-compose exec backend python -c "print('Hello')"

# 重启服务
docker-compose restart postgres         # 重启特定服务
docker-compose restart                  # 重启所有服务
```

---

## 🎓 最佳实践建议

### 开发阶段

1. ✅ 使用混合模式（Docker数据库 + 本地代码）
2. ✅ 经常提交代码到Git
3. ✅ 定期备份数据库
4. ✅ 使用`.env.development`管理开发配置

### 测试阶段

1. ✅ 使用完全Docker模式测试
2. ✅ 模拟生产环境配置
3. ✅ 压力测试和性能测试
4. ✅ 备份测试数据

### 生产阶段

1. ✅ 使用完全Docker模式部署
2. ✅ 配置自动重启和健康检查
3. ✅ 设置定期备份（每天）
4. ✅ 配置监控和告警
5. ✅ 使用强密码和安全配置
6. ✅ 定期更新系统和依赖

---

## 🆘 获取帮助

如果遇到问题，请按以下顺序尝试：

1. 查看[常见问题](#常见问题解决)
2. 查看[完整Docker部署文档](DOCKER_DEPLOYMENT.md)
3. 检查[项目Issues](https://github.com/your-repo/issues)
4. 查看Docker日志: `docker-compose logs -f`

---

**祝您部署顺利！** 🎉

