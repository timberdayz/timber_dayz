# 快速部署指南 - 腾讯云2核4G服务器

**版本**: v4.19.7  
**适用场景**: 单服务器部署（测试和生产共用）  
**更新时间**: 2025-01-XX

---

## 🎯 部署前准备

### 1. 服务器准备（已完成）

根据用户反馈，已完成：
- ✅ 服务器基础更新
- ✅ 软件安装
- ✅ GitHub Actions测试
- ✅ GitHub Secrets配置

### 2. 确认服务器信息

- **服务器IP**: `你的服务器IP地址`
- **SSH用户名**: `root` 或 `ubuntu`
- **项目路径**: `/opt/xihong_erp`（建议）

---

## 📋 开发环境 vs 生产环境配置差异

### 核心差异（必须修改）

| 配置项 | 开发环境 | 生产环境 | 说明 |
|--------|---------|---------|------|
| **ENVIRONMENT** | `development` | `production` | ⭐ 核心标识 |
| **APP_ENV** | `development` | `production` | 应用环境 |
| **HOST** | `127.0.0.1` | `0.0.0.0` | 允许外部访问 |
| **ALLOWED_ORIGINS** | `http://localhost:...` | `http://your-server-ip` | 仅允许实际地址 |
| **ALLOWED_HOSTS** | `localhost,127.0.0.1` | `your-server-ip` | 安全限制 |
| **VITE_API_URL** | `http://localhost:8001` | `http://your-server-ip:8000` | 前端API地址 |
| **VITE_MODE** | `development` | `production` | 构建模式 |

### 安全配置（必须修改）

| 配置项 | 开发环境 | 生产环境 | 说明 |
|--------|---------|---------|------|
| **POSTGRES_PASSWORD** | `erp_pass_2025` | `强随机密码24位+` | ⚠️ 必须修改 |
| **SECRET_KEY** | `默认值` | `32位随机字符串` | ⚠️ 必须修改 |
| **JWT_SECRET_KEY** | `默认值` | `32位随机字符串` | ⚠️ 必须修改 |
| **ACCOUNT_ENCRYPTION_KEY** | `空` | `Fernet密钥` | 建议设置 |
| **REDIS_PASSWORD** | `空` | `强随机密码16位+` | ⚠️ 必须修改 |

### 性能优化（2核4G服务器）

| 配置项 | 开发环境 | 生产环境 | 说明 |
|--------|---------|---------|------|
| **DB_POOL_SIZE** | `20` | `10` | 资源优化 |
| **DB_MAX_OVERFLOW** | `40` | `20` | 资源优化 |
| **MAX_CONCURRENT_TASKS** | `3` | `2` | 资源优化 |

### 功能配置

| 配置项 | 开发环境 | 生产环境 | 说明 |
|--------|---------|---------|------|
| **PLAYWRIGHT_HEADLESS** | `false` | `true` | 无头模式 |
| **LOG_LEVEL** | `INFO` | `INFO` | 日志级别 |
| **DATABASE_ECHO** | `false` | `false` | 禁止SQL日志 |

---

## 🚀 部署步骤

### 步骤1：在服务器上准备项目

```bash
# 1. SSH登录服务器
ssh user@your-server-ip

# 2. 创建项目目录
sudo mkdir -p /opt/xihong_erp
sudo chown $USER:$USER /opt/xihong_erp
cd /opt/xihong_erp

# 3. 克隆项目代码
git clone https://github.com/timberdayz/timber_dayz.git .

# 4. 创建必要的目录
mkdir -p data logs temp uploads downloads config backups
```

### 步骤2：配置生产环境.env文件

```bash
# 1. 复制生产环境配置模板
cp env.production.cloud.example .env

# 2. 生成密码和密钥（在本地或服务器上）
python scripts/check_passwords_and_registry.py --generate

# 3. 编辑配置文件
nano .env
```

**必须修改的配置**：

```bash
# 1. 环境标识
ENVIRONMENT=production
APP_ENV=production

# 2. 数据库密码（使用生成的强密码）
POSTGRES_PASSWORD=你的强密码_至少24位
DATABASE_URL=postgresql://erp_user:你的强密码@postgres:5432/xihong_erp

# 3. 安全密钥（使用生成的密钥）
SECRET_KEY=你的32位随机字符串
JWT_SECRET_KEY=你的32位随机字符串
ACCOUNT_ENCRYPTION_KEY=你的Fernet密钥

# 4. Redis密码（使用生成的强密码）
REDIS_PASSWORD=你的Redis密码_至少16位
REDIS_URL=redis://:你的Redis密码@redis:6379/0
CELERY_BROKER_URL=redis://:你的Redis密码@redis:6379/0
CELERY_RESULT_BACKEND=redis://:你的Redis密码@redis:6379/0

# 5. 服务器配置（修改为实际IP）
ALLOWED_ORIGINS=http://你的服务器IP
ALLOWED_HOSTS=你的服务器IP
VITE_API_URL=http://你的服务器IP:8000
```

### 步骤3：首次部署（手动）

```bash
# 1. 登录GitHub镜像仓库
docker login ghcr.io
# 用户名: 你的GitHub用户名
# 密码: GitHub Personal Access Token（需要packages:read权限）

# 2. 拉取镜像
docker pull ghcr.io/timberdayz/timber_dayz/backend:latest
docker pull ghcr.io/timberdayz/timber_dayz/frontend:latest

# 3. 标记镜像
docker tag ghcr.io/timberdayz/timber_dayz/backend:latest xihong_erp_backend:latest
docker tag ghcr.io/timberdayz/timber_dayz/frontend:latest xihong_erp_frontend:latest

# 4. 启动服务（使用云服务器优化配置）
docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml --profile production up -d

# 5. 查看日志
docker-compose logs -f

# 6. 健康检查
curl http://localhost:8000/health
```

### 步骤4：配置GitHub Actions自动部署

**GitHub Secrets已配置**（根据用户反馈）：
- ✅ `PRODUCTION_SSH_PRIVATE_KEY`
- ✅ `PRODUCTION_HOST`
- ✅ `PRODUCTION_USER`
- ✅ `PRODUCTION_PATH`

**触发部署**：

1. **手动触发**（推荐首次测试）：
   - 打开GitHub仓库: https://github.com/timberdayz/timber_dayz
   - 进入 **Actions** → **Deploy to Production**
   - 点击 **Run workflow**
   - 输入参数：
     - `image_tag`: `latest`
     - `confirm`: `DEPLOY`
   - 点击 **Run workflow**

2. **自动触发**（推送版本标签）：
   ```bash
   git tag v4.19.7
   git push origin v4.19.7
   ```

---

## 🔄 CI/CD更新流程

### 工作流程

```
代码提交 → GitHub Actions CI → Docker构建 → 推送镜像 → 自动部署
```

### 详细流程

1. **代码提交到main分支**
   - 触发CI Pipeline（测试、代码检查）
   - 触发Docker Build and Push（构建镜像）

2. **镜像构建完成**
   - 镜像推送到 `ghcr.io/timberdayz/timber_dayz/backend:latest`
   - 镜像推送到 `ghcr.io/timberdayz/timber_dayz/frontend:latest`

3. **部署触发**
   - 手动触发：GitHub Actions UI → Run workflow
   - 自动触发：推送版本标签 `v*`

4. **服务器部署**
   - SSH连接到服务器
   - 拉取最新镜像
   - 使用docker-compose部署
   - 健康检查验证

---

## 📊 配置差异详细对比

### 1. 环境标识

**开发环境**：
```bash
ENVIRONMENT=development
APP_ENV=development
DEBUG=false
```

**生产环境**：
```bash
ENVIRONMENT=production  # ⭐ 必须修改
APP_ENV=production      # ⭐ 必须修改
DEBUG=false
```

### 2. 网络配置

**开发环境**：
```bash
HOST=127.0.0.1
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:5174
ALLOWED_HOSTS=localhost,127.0.0.1
VITE_API_URL=http://localhost:8001
```

**生产环境**：
```bash
HOST=0.0.0.0                    # ⭐ 允许外部访问
ALLOWED_ORIGINS=http://your-server-ip  # ⭐ 仅允许实际地址
ALLOWED_HOSTS=your-server-ip     # ⭐ 安全限制
VITE_API_URL=http://your-server-ip:8000  # ⭐ 服务器地址
```

### 3. 安全配置

**开发环境**（使用默认值，仅开发）：
```bash
POSTGRES_PASSWORD=erp_pass_2025
SECRET_KEY=xihong-erp-secret-key-2025
JWT_SECRET_KEY=xihong-erp-jwt-secret-2025
REDIS_PASSWORD=  # 空
```

**生产环境**（必须使用强密码）：
```bash
POSTGRES_PASSWORD=你的强随机密码_至少24位  # ⚠️ 必须修改
SECRET_KEY=你的32位随机字符串              # ⚠️ 必须修改
JWT_SECRET_KEY=你的32位随机字符串          # ⚠️ 必须修改
ACCOUNT_ENCRYPTION_KEY=你的Fernet密钥      # 建议设置
REDIS_PASSWORD=你的强随机密码_至少16位      # ⚠️ 必须修改
```

### 4. 性能配置（2核4G优化）

**开发环境**：
```bash
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=40
MAX_CONCURRENT_TASKS=3
```

**生产环境**（2核4G优化）：
```bash
DB_POOL_SIZE=10          # ⭐ 从20降到10
DB_MAX_OVERFLOW=20       # ⭐ 从40降到20
MAX_CONCURRENT_TASKS=2   # ⭐ 从3降到2
```

### 5. 功能配置

**开发环境**：
```bash
PLAYWRIGHT_HEADLESS=false  # 可以看到浏览器
VITE_MODE=development      # 开发模式
LOG_LEVEL=INFO
```

**生产环境**：
```bash
PLAYWRIGHT_HEADLESS=true   # ⭐ 无头模式
VITE_MODE=production       # ⭐ 生产模式
LOG_LEVEL=INFO
```

---

## ✅ 部署检查清单

### 服务器配置

- [ ] Docker和Docker Compose已安装
- [ ] 项目代码已克隆到服务器
- [ ] `.env`文件已配置（生产环境配置）
- [ ] 所有密码已修改为强密码
- [ ] 服务器IP地址已配置
- [ ] 服务器已登录GitHub镜像仓库

### GitHub配置

- [x] GitHub Secrets已配置（用户反馈已完成）
- [ ] 测试部署工作流（手动触发）

### 部署验证

- [ ] 服务启动成功
- [ ] 健康检查通过: `curl http://localhost:8000/health`
- [ ] 前端访问正常: `curl http://localhost:80`
- [ ] 数据库连接正常
- [ ] Redis连接正常

---

## 🔧 故障排查

### 问题1：镜像拉取失败

```bash
# 检查是否已登录GitHub
docker login ghcr.io

# 检查镜像是否存在
docker pull ghcr.io/timberdayz/timber_dayz/backend:latest
```

### 问题2：服务启动失败

```bash
# 查看日志
docker-compose logs backend
docker-compose logs postgres

# 检查环境变量
docker-compose config
```

### 问题3：健康检查失败

```bash
# 检查服务状态
docker-compose ps

# 手动健康检查
curl http://localhost:8000/health

# 查看容器日志
docker logs xihong_erp_backend
```

---

## 📚 相关文档

- [环境配置对比](./ENV_DEVELOPMENT_VS_PRODUCTION.md)
- [生产环境配置指南](./PRODUCTION_ENV_CONFIG.md)
- [部署测试报告](./DEPLOYMENT_TEST_REPORT.md)
- [CI/CD流程指南](./CI_CD_GUIDE.md)

---

**最后更新**: 2025-01-XX
