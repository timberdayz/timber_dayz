# 西虹ERP系统 - Docker部署完整指南

[![Docker](https://img.shields.io/badge/Docker-20.10+-blue.svg)](https://www.docker.com/)
[![Docker Compose](https://img.shields.io/badge/Docker%20Compose-2.0+-blue.svg)](https://docs.docker.com/compose/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue.svg)](https://www.postgresql.org/)

> **v4.0.0** - 2025-10-23  
> 一键部署，云端迁移零成本

---

## 📋 目录

- [快速开始](#快速开始)
- [部署模式](#部署模式)
- [环境要求](#环境要求)
- [开发环境部署](#开发环境部署)
- [生产环境部署](#生产环境部署)
- [配置说明](#配置说明)
- [常用命令](#常用命令)
- [故障排除](#故障排除)
- [云端迁移](#云端迁移)
- [性能优化](#性能优化)
- [安全建议](#安全建议)

---

## ⚡ 快速开始

### 🖥️ Windows用户

```bash
# 1. 克隆代码
git clone <your-repo-url>
cd xihong_erp

# 2. 启动开发环境（仅数据库）
docker\scripts\start-dev.bat

# 3. 启动生产环境（完整系统）
docker\scripts\start-prod.bat
```

### 🐧 Linux/Mac用户

```bash
# 1. 克隆代码
git clone <your-repo-url>
cd xihong_erp

# 2. 启动开发环境（仅数据库）
chmod +x docker/scripts/*.sh
./docker/scripts/start-dev.sh

# 3. 启动生产环境（完整系统）
./docker/scripts/start-prod.sh

# 或使用Makefile
make dev      # 开发环境
make prod     # 生产环境
```

---

## 🎯 部署模式

西虹ERP系统支持三种部署模式：

### 1. 开发模式（推荐本地开发）

**服务组成**：
- ✅ PostgreSQL数据库
- ✅ pgAdmin管理界面
- ⚠️ 后端和前端在本地运行（方便调试）

**适用场景**：
- 本地开发和测试
- 频繁修改代码
- 需要调试功能

**启动方式**：
```bash
# Windows
docker\scripts\start-dev.bat

# Linux/Mac
make dev
# 或
./docker/scripts/start-dev.sh
```

**访问地址**：
- PostgreSQL: `localhost:5432`
- pgAdmin: `http://localhost:5051`
- 后端（手动启动）: `http://localhost:8000`
- 前端（手动启动）: `http://localhost:5173`

---

### 2. 生产模式（推荐部署）

**服务组成**：
- ✅ PostgreSQL数据库
- ✅ FastAPI后端（容器化）
- ✅ Vue.js前端（Nginx容器化）
- ⚠️ pgAdmin默认禁用（安全考虑）

**适用场景**：
- 生产环境部署
- 团队协作开发
- 云端部署
- 性能优化需求

**启动方式**：
```bash
# Windows
docker\scripts\start-prod.bat

# Linux/Mac
make prod
# 或
./docker/scripts/start-prod.sh
```

**访问地址**：
- 前端: `http://localhost:5174`
- 后端API: `http://localhost:8001`
- API文档: `http://localhost:8001/api/docs`

---

### 3. 完整模式（开发+生产）

**服务组成**：
- ✅ PostgreSQL数据库
- ✅ FastAPI后端
- ✅ Vue.js前端
- ✅ pgAdmin管理界面

**启动方式**：
```bash
docker-compose --profile full up -d
```

---

## 💻 环境要求

### 最低配置

| 项目 | 要求 |
|------|------|
| 操作系统 | Windows 10/11, macOS 10.14+, Ubuntu 20.04+ |
| Docker | 20.10+ |
| Docker Compose | 2.0+ |
| 内存 | 4GB |
| 磁盘空间 | 10GB |

### 推荐配置（生产环境）

| 项目 | 推荐 |
|------|------|
| 操作系统 | Ubuntu 22.04 LTS / CentOS 8+ |
| Docker | 最新稳定版 |
| Docker Compose | 最新稳定版 |
| 内存 | 8GB+ |
| 磁盘空间 | 50GB SSD |
| CPU | 4核+ |

### 安装Docker

#### Windows

1. 下载并安装 [Docker Desktop](https://www.docker.com/products/docker-desktop)
2. 启动Docker Desktop
3. 验证安装：
```powershell
docker --version
docker-compose --version
```

#### Linux

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# 安装Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 验证安装
docker --version
docker-compose --version
```

#### macOS

```bash
# 使用Homebrew
brew install --cask docker

# 或下载安装包
# https://www.docker.com/products/docker-desktop
```

---

## 🛠️ 开发环境部署

### 步骤1：准备环境

```bash
# 克隆代码
git clone <your-repo-url>
cd xihong_erp

# 复制环境变量文件
cp env.development.example .env

# 编辑配置（可选）
# Windows: notepad .env
# Linux/Mac: nano .env
```

### 步骤2：启动数据库服务

#### Windows

```bash
# 方式1：使用启动脚本（推荐）
docker\scripts\start-dev.bat

# 方式2：使用Docker Compose
docker-compose --profile dev up -d

# 方式3：使用Makefile（需要安装make）
make dev
```

#### Linux/Mac

```bash
# 方式1：使用启动脚本（推荐）
chmod +x docker/scripts/start-dev.sh
./docker/scripts/start-dev.sh

# 方式2：使用Makefile（推荐）
make dev

# 方式3：使用Docker Compose
docker-compose --profile dev up -d
```

### 步骤3：初始化数据库

数据库会自动初始化，如需手动初始化：

```bash
# Python方式
python docker/postgres/init-tables.py

# Makefile方式
make db-init
```

### 步骤4：启动后端（本地）

```bash
# 进入后端目录
cd backend

# 安装依赖（首次）
pip install -r requirements.txt

# 启动后端服务
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 步骤5：启动前端（本地）

```bash
# 进入前端目录
cd frontend

# 安装依赖（首次）
npm install

# 启动前端服务
npm run dev
```

### 步骤6：访问系统

- **前端界面**: http://localhost:5173
- **后端API**: http://localhost:8000
- **API文档**: http://localhost:8000/api/docs
- **PostgreSQL**: localhost:5432
- **pgAdmin**: http://localhost:5051

**pgAdmin登录信息**：
- 邮箱: `dev@xihong.com`
- 密码: `dev123`

**数据库连接信息**：
- 主机: `localhost`
- 端口: `5432`
- 数据库: `xihong_erp_dev`
- 用户名: `erp_dev`
- 密码: `dev_pass_2025`

---

## 🚀 生产环境部署

### 步骤1：准备环境变量

```bash
# 复制生产环境配置
cp env.production.example .env

# 编辑配置（必须修改密码和密钥！）
nano .env
```

**⚠️ 重要：必须修改以下配置**

```bash
# 数据库密码
POSTGRES_PASSWORD=YOUR_SECURE_PASSWORD_HERE

# API密钥（至少32位随机字符串）
SECRET_KEY=YOUR_SECRET_KEY_CHANGE_THIS_TO_RANDOM_STRING

# pgAdmin密码
PGADMIN_PASSWORD=YOUR_PGADMIN_PASSWORD_HERE

# 允许的域名
ALLOWED_ORIGINS=https://your-domain.com,https://www.your-domain.com

# 前端API地址
VITE_API_URL=https://your-domain.com/api
```

### 步骤2：构建并启动

#### Windows

```bash
# 使用启动脚本（推荐）
docker\scripts\start-prod.bat

# 手动启动
docker build -f Dockerfile.backend -t xihong-erp-backend:latest .
docker build -f Dockerfile.frontend -t xihong-erp-frontend:latest .
docker-compose --profile production up -d
```

#### Linux/Mac

```bash
# 方式1：使用启动脚本（推荐）
chmod +x docker/scripts/start-prod.sh
./docker/scripts/start-prod.sh

# 方式2：使用Makefile（推荐）
make build      # 构建镜像
make prod       # 启动服务

# 方式3：手动执行
docker build -f Dockerfile.backend -t xihong-erp-backend:latest .
docker build -f Dockerfile.frontend -t xihong-erp-frontend:latest .
docker-compose --profile production up -d
```

### 步骤3：健康检查

```bash
# 使用健康检查脚本
chmod +x docker/scripts/health-check.sh
./docker/scripts/health-check.sh

# 或使用Makefile
make health

# 手动检查
curl http://localhost:8001/health
curl http://localhost:5174
```

### 步骤4：访问系统

- **前端界面**: http://localhost:5174
- **后端API**: http://localhost:8001
- **API文档**: http://localhost:8001/api/docs

---

## ⚙️ 配置说明

### 端口配置

系统默认端口已优化以避免冲突：

| 服务 | 默认端口 | 说明 |
|------|---------|------|
| 前端 | 5174 | 避免与Vite开发服务器(5173)冲突 |
| 后端 | 8001 | 避免与常见Python服务(8000)冲突 |
| PostgreSQL | 5432 | 标准PostgreSQL端口 |
| pgAdmin | 5051 | 避免与其他管理工具(5050)冲突 |

**修改端口**：

在`.env`文件中修改：

```bash
BACKEND_PORT=8001
FRONTEND_PORT=5174
POSTGRES_PORT=5432
PGADMIN_PORT=5051
```

### 数据库配置

#### PostgreSQL连接池

```bash
# .env文件
DB_POOL_SIZE=20          # 连接池大小
DB_MAX_OVERFLOW=40       # 最大溢出连接
DB_POOL_TIMEOUT=30       # 连接超时（秒）
DB_POOL_RECYCLE=3600     # 连接回收时间（秒）
```

#### 开发vs生产

```bash
# 开发环境
DATABASE_URL=postgresql://erp_dev:dev_pass_2025@localhost:5432/xihong_erp_dev
DATABASE_ECHO=true       # 显示SQL语句

# 生产环境
DATABASE_URL=postgresql://erp_user:STRONG_PASSWORD@postgres:5432/xihong_erp
DATABASE_ECHO=false      # 不显示SQL语句
```

### 资源限制

在`docker-compose.yml`中配置：

```yaml
deploy:
  resources:
    limits:
      cpus: '2'           # CPU限制
      memory: 2G          # 内存限制
    reservations:
      cpus: '0.5'         # 预留CPU
      memory: 512M        # 预留内存
```

---

## 📝 常用命令

### 服务管理

```bash
# 启动服务
docker-compose up -d                    # 后台启动
docker-compose --profile dev up -d      # 开发模式
docker-compose --profile production up -d  # 生产模式

# 停止服务
docker-compose stop                     # 停止（不删除容器）
docker-compose down                     # 停止并删除容器
docker-compose down -v                  # 停止并删除数据卷

# 重启服务
docker-compose restart                  # 重启所有服务
docker-compose restart backend          # 重启后端
docker-compose restart frontend         # 重启前端

# 查看状态
docker-compose ps                       # 查看服务状态
docker-compose logs -f                  # 查看日志
docker-compose logs -f backend          # 查看后端日志
```

### 容器操作

```bash
# 进入容器
docker-compose exec backend /bin/bash   # 进入后端容器
docker-compose exec postgres psql -U erp_user -d xihong_erp  # 数据库shell

# 查看资源使用
docker stats                            # 实时资源监控
make stats                              # 查看容器资源

# 清理
docker system prune -a                  # 清理所有未使用资源
docker volume prune                     # 清理未使用数据卷
```

### 数据库操作

```bash
# 备份数据库
make db-backup
# 或
docker-compose exec -T postgres pg_dump -U erp_user xihong_erp > backup.sql

# 恢复数据库
docker-compose exec -T postgres psql -U erp_user -d xihong_erp < backup.sql

# 进入数据库
make db-shell
# 或
docker-compose exec postgres psql -U erp_user -d xihong_erp
```

### Makefile命令（推荐）

```bash
# 开发
make dev          # 启动开发环境
make dev-full     # 启动完整开发环境

# 生产
make build        # 构建镜像
make prod         # 启动生产环境

# 管理
make stop         # 停止服务
make restart      # 重启服务
make logs         # 查看日志
make health       # 健康检查
make ps           # 查看状态

# 数据库
make db-init      # 初始化数据库
make db-backup    # 备份数据库
make db-shell     # 数据库shell

# 清理
make clean        # 清理容器
make clean-all    # 清理所有
```

---

## 🔧 故障排除

### 1. Docker服务无法启动

**症状**：
```bash
Cannot connect to the Docker daemon
```

**解决方案**：
```bash
# Windows
# 启动Docker Desktop应用

# Linux
sudo systemctl start docker
sudo systemctl enable docker

# 验证
docker info
```

### 2. 端口被占用

**症状**：
```bash
Error: Bind for 0.0.0.0:5432 failed: port is already allocated
```

**解决方案**：

```bash
# 方式1：修改端口（推荐）
# 编辑.env文件
POSTGRES_PORT=5433  # 改为其他端口

# 方式2：找到占用端口的进程并关闭
# Windows
netstat -ano | findstr :5432
taskkill /PID <PID> /F

# Linux
lsof -i:5432
kill -9 <PID>
```

### 3. 数据库连接失败

**症状**：
```bash
FATAL: password authentication failed for user "erp_user"
```

**解决方案**：

```bash
# 1. 检查.env文件配置是否正确
cat .env | grep POSTGRES

# 2. 重新创建数据库容器
docker-compose down
docker volume rm xihong_erp_postgres_data
docker-compose up -d postgres

# 3. 查看数据库日志
docker-compose logs postgres
```

### 4. 前端无法访问后端API

**症状**：
```bash
Network Error / CORS Error
```

**解决方案**：

```bash
# 1. 检查后端是否启动
curl http://localhost:8001/health

# 2. 检查CORS配置
# 编辑.env文件
ALLOWED_ORIGINS=http://localhost:5174,http://localhost:80

# 3. 重启后端
docker-compose restart backend
```

### 5. 镜像构建失败

**症状**：
```bash
ERROR: failed to solve: executor failed running
```

**解决方案**：

```bash
# 1. 清理Docker缓存
docker system prune -a

# 2. 重新构建（不使用缓存）
docker build --no-cache -f Dockerfile.backend -t xihong-erp-backend:latest .

# 3. 检查网络连接
docker run --rm alpine ping -c 4 8.8.8.8
```

### 6. 容器内存不足

**症状**：
```bash
Container killed (OOMKilled)
```

**解决方案**：

```bash
# 1. 增加Docker内存限制
# Docker Desktop → Settings → Resources → Memory

# 2. 调整容器资源限制
# 编辑docker-compose.yml
deploy:
  resources:
    limits:
      memory: 4G  # 增加到4GB
```

---

## ☁️ 云端迁移

### 阿里云ECS部署

#### 1. 准备服务器

```bash
# 登录服务器
ssh root@your-server-ip

# 安装Docker
curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun
systemctl start docker
systemctl enable docker

# 安装Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
```

#### 2. 部署应用

```bash
# 克隆代码
git clone <your-repo-url>
cd xihong_erp

# 配置环境变量
cp env.production.example .env
nano .env  # 修改配置

# 启动服务
./docker/scripts/start-prod.sh

# 或使用Makefile
make prod
```

#### 3. 配置Nginx反向代理

```nginx
# /etc/nginx/sites-available/xihong-erp
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:5174;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api/ {
        proxy_pass http://localhost:8001/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
# 启用配置
ln -s /etc/nginx/sites-available/xihong-erp /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

#### 4. 配置SSL证书（Let's Encrypt）

```bash
# 安装Certbot
apt-get install certbot python3-certbot-nginx

# 获取证书
certbot --nginx -d your-domain.com -d www.your-domain.com

# 自动续期
crontab -e
# 添加：0 0 * * * certbot renew --quiet
```

### 腾讯云部署

与阿里云类似，主要区别：

```bash
# 使用腾讯云Docker镜像加速
curl -fsSL https://get.docker.com | bash -s docker --mirror Tencent
```

### AWS部署

```bash
# 使用AWS ECR（可选）
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin your-account-id.dkr.ecr.us-east-1.amazonaws.com

# 推送镜像
docker tag xihong-erp-backend:latest your-account-id.dkr.ecr.us-east-1.amazonaws.com/xihong-erp-backend:latest
docker push your-account-id.dkr.ecr.us-east-1.amazonaws.com/xihong-erp-backend:latest
```

---

## ⚡ 性能优化

### 1. PostgreSQL优化

```sql
-- 连接数据库
psql -U erp_user -d xihong_erp

-- 优化配置
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET work_mem = '16MB';
ALTER SYSTEM SET maintenance_work_mem = '128MB';
ALTER SYSTEM SET effective_cache_size = '1GB';

-- 重启PostgreSQL
docker-compose restart postgres
```

### 2. 前端优化

```bash
# 使用生产构建
npm run build

# 启用Gzip压缩（已在Nginx配置中启用）
# docker/nginx/default.conf
```

### 3. 后端优化

```bash
# 使用多Worker
# docker-compose.yml
command: uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 4. Docker优化

```bash
# 使用BuildKit加速构建
export DOCKER_BUILDKIT=1

# 多阶段构建减小镜像体积（已实现）
# Dockerfile.backend和Dockerfile.frontend已使用多阶段构建
```

---

## 🔒 安全建议

### 1. 修改默认密码

```bash
# ⚠️ 必须修改这些默认密码
POSTGRES_PASSWORD=YOUR_STRONG_PASSWORD    # 数据库密码
SECRET_KEY=YOUR_RANDOM_32_CHAR_STRING     # API密钥
PGADMIN_PASSWORD=YOUR_ADMIN_PASSWORD      # pgAdmin密码
```

### 2. 限制端口访问

```bash
# 使用防火墙限制访问
ufw allow 80/tcp      # HTTP
ufw allow 443/tcp     # HTTPS
ufw deny 5432/tcp     # 禁止外部访问数据库
```

### 3. 使用HTTPS

```bash
# 参见"云端迁移 - 配置SSL证书"部分
```

### 4. 定期备份

```bash
# 创建自动备份脚本
crontab -e
# 每天凌晨2点备份
0 2 * * * /path/to/xihong_erp/docker/scripts/backup.sh
```

### 5. 监控日志

```bash
# 定期检查日志
docker-compose logs --tail=100 backend | grep ERROR
docker-compose logs --tail=100 postgres | grep FATAL
```

---

## 📞 获取帮助

- **文档**: 查看`docs/`目录下的其他文档
- **健康检查**: `make health` 或 `./docker/scripts/health-check.sh`
- **日志查看**: `make logs` 或 `docker-compose logs -f`
- **问题反馈**: 提交Issue到项目仓库

---

## 📜 更新日志

### v4.0.0 (2025-10-23)
- ✅ 完整的Docker Compose配置
- ✅ 支持开发/生产模式切换
- ✅ 优化端口配置避免冲突
- ✅ 完整的启动脚本（Windows/Linux）
- ✅ 健康检查和监控脚本
- ✅ PostgreSQL自动初始化
- ✅ 数据持久化方案
- ✅ 完整的部署文档

---

**最后更新**: 2025-10-23  
**维护者**: 西虹ERP团队

