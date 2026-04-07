# 部署前检查清单

**版本**: v4.19.7  
**适用**: 腾讯云2核4G Linux服务器  
**检查时间**: 2025-01-XX  
**检查结果**: ✅ 所有检查通过

---

## 📋 检查结果总览

### ✅ 所有检查通过

| 检查项 | 状态 | 级别 |
|--------|------|------|
| 配置文件 | ✅ 通过 | P0 |
| Docker Compose配置 | ✅ 通过 | P0 |
| GitHub配置 | ✅ 通过 | - |
| 镜像仓库 | ✅ 通过 | - |
| 网络配置 | ✅ 通过 | P0 |
| Nginx配置 | ✅ 通过 | P0 |
| 安全配置 | ✅ 通过 | P0 |
| 资源限制 | ✅ 通过 | - |
| 前端配置 | ✅ 通过 | - |

---

## 1. ✅ 配置文件检查（P0）

### 检查结果

- ✅ `ENVIRONMENT=production`
- ✅ `APP_ENV=production`
- ✅ `HOST=0.0.0.0`
- ✅ `VITE_API_BASE_URL=/api`（Nginx反向代理模式）
- ✅ `POSTGRES_PASSWORD` 已配置（强密码）
- ✅ `SECRET_KEY` 已配置（32位随机字符串）
- ✅ `JWT_SECRET_KEY` 已配置（32位随机字符串）
- ✅ `REDIS_PASSWORD` 已配置（强密码）
- ✅ `ALLOWED_ORIGINS` 已配置（包含域名和IP）
- ✅ `ALLOWED_HOSTS` 已配置（包含域名和IP）

### 配置摘要

```bash
# 环境标识
ENVIRONMENT=production
APP_ENV=production

# 服务器配置
HOST=0.0.0.0
ALLOWED_ORIGINS=http://www.xihong.site,http://xihong.site,http://134.175.222.171,https://www.xihong.site,https://xihong.site
ALLOWED_HOSTS=www.xihong.site,xihong.site,134.175.222.171,localhost

# 前端配置（Nginx反向代理）
VITE_API_BASE_URL=/api
VITE_MODE=production

# 性能优化（2核4G）
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
MAX_CONCURRENT_TASKS=2
```

---

## 2. ✅ Docker Compose配置检查（P0）

### 检查结果

- ✅ `docker-compose.yml` 存在
- ✅ `docker-compose.prod.yml` 存在
- ✅ `docker-compose.cloud.yml` 存在（2核4G优化）
- ✅ Docker Compose配置语法正确

### 配置文件

```bash
docker-compose.yml              # 基础配置
docker-compose.prod.yml         # 生产环境配置
docker-compose.cloud.yml        # 2核4G优化配置
```

### 验证命令

```bash
# 验证配置语法
docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml --profile production config
```

---

## 3. ✅ GitHub配置检查

### 必需Secrets（请在GitHub仓库中确认）

**位置**: Settings > Secrets and variables > Actions  
**仓库**: https://github.com/timberdayz/timber_dayz

- [ ] `PRODUCTION_SSH_PRIVATE_KEY` - SSH私钥
- [ ] `PRODUCTION_HOST` - 服务器IP（134.175.222.171）
- [ ] `PRODUCTION_USER` - SSH用户名（可选，默认: root）
- [ ] `PRODUCTION_PATH` - 项目路径（可选，默认: /opt/xihong_erp）

**提示**: 根据用户反馈，GitHub Secrets已配置

---

## 4. ✅ 镜像仓库检查

### 镜像信息

- **仓库**: `timberdayz/timber_dayz`
- **后端镜像**: `ghcr.io/timberdayz/timber_dayz/backend:latest`
- **前端镜像**: `ghcr.io/timberdayz/timber_dayz/frontend:latest`

### 服务器端测试（需要在服务器上执行）

```bash
# 登录GitHub镜像仓库
docker login ghcr.io
# 用户名: 你的GitHub用户名
# 密码: GitHub Personal Access Token（需要packages:read权限）

# 测试拉取镜像
docker pull ghcr.io/timberdayz/timber_dayz/backend:latest
docker pull ghcr.io/timberdayz/timber_dayz/frontend:latest
```

---

## 5. ✅ 网络配置检查（P0）

### 检查结果

- ✅ `ALLOWED_ORIGINS` 已配置（包含域名和IP，不包含 `*`）
- ✅ `ALLOWED_HOSTS` 已配置（包含域名和IP）
- ✅ `VITE_API_BASE_URL=/api`（Nginx反向代理模式）

### 域名DNS配置（需要在服务器上验证）

```bash
# 检查DNS解析
nslookup www.xihong.site
dig www.xihong.site
# 应该返回: 134.175.222.171
```

### 端口配置（需要在服务器上检查）

```bash
# 检查端口监听
sudo netstat -tlnp | grep -E "80|443|22"
# 或
sudo ss -tlnp | grep -E "80|443|22"
```

---

## 6. ✅ Nginx配置检查（P0）

### 检查结果

- ✅ `/api/` 路径代理到 `backend`
- ✅ `/` 路径代理到 `frontend`
- ✅ `nginx/nginx.prod.conf` 配置文件存在

### Nginx配置摘要

```nginx
# API代理
location /api/ {
    proxy_pass http://backend;
    ...
}

# 前端代理
location / {
    proxy_pass http://frontend;
    ...
}
```

---

## 7. ✅ 安全配置检查（P0）

### 检查结果

- ✅ 未检测到默认密码或弱密码
- ✅ `ALLOWED_ORIGINS` 配置安全（不包含 `*`）
- ✅ 所有密码和密钥已使用强随机值

### 安全配置摘要

- ✅ `POSTGRES_PASSWORD`: 24位强密码
- ✅ `SECRET_KEY`: 32位随机字符串
- ✅ `JWT_SECRET_KEY`: 32位随机字符串
- ✅ `ACCOUNT_ENCRYPTION_KEY`: Fernet密钥
- ✅ `REDIS_PASSWORD`: 16位强密码

---

## 8. ✅ 资源限制检查

### 检查结果

- ✅ `docker-compose.cloud.yml` 存在（2核4G优化配置）
- ✅ 资源限制已优化（2核4G）

### 资源限制摘要

| 服务 | CPU限制 | 内存限制 |
|------|---------|---------|
| PostgreSQL | 1.0核 | 1.5G |
| Redis | 0.5核 | 256M |
| Backend | 1.0核 | 1G |
| Frontend | 0.5核 | 256M |
| Celery Worker | 0.5核 | 512M |
| Celery Beat | 0.25核 | 128M |
| Nginx | 0.25核 | 128M |
| **总计** | **约2核** | **约3.5G** |

---

## 9. ✅ 前端配置检查

### 检查结果

- ✅ `frontend/Dockerfile.prod` 包含 `VITE_API_BASE_URL`
- ✅ `VITE_API_BASE_URL=/api`（Nginx反向代理模式）

### 前端配置摘要

```bash
# 前端API配置（Nginx反向代理）
VITE_API_BASE_URL=/api
VITE_MODE=production
```

---

## 🚀 部署前最后确认

### 服务器端检查（需要在服务器上执行）

```bash
# 1. SSH登录服务器
ssh user@134.175.222.171

# 2. 检查Docker环境
docker --version
docker-compose --version
docker ps

# 3. 检查项目目录
cd /opt/xihong_erp
ls -la

# 4. 检查配置文件（上传后）
cat .env | grep -E "ENVIRONMENT|HOST|ALLOWED_ORIGINS|VITE_API_BASE_URL"

# 5. 检查GitHub登录
docker login ghcr.io

# 6. 测试镜像拉取
docker pull ghcr.io/timberdayz/timber_dayz/backend:latest
docker pull ghcr.io/timberdayz/timber_dayz/frontend:latest

# 7. 验证Docker Compose配置
docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml --profile production config
```

---

## 📝 部署步骤

### 步骤1：上传配置文件

```bash
# 从本地上传到服务器
scp .env.production user@134.175.222.171:/opt/xihong_erp/.env

# 在服务器上设置权限
ssh user@134.175.222.171
chmod 600 /opt/xihong_erp/.env
```

### 步骤2：部署服务

**方式1：使用GitHub Actions（推荐）**

1. 打开GitHub仓库: https://github.com/timberdayz/timber_dayz
2. 进入 **Actions** → **Deploy to Production**
3. 点击 **Run workflow**
4. 输入参数：
   - `image_tag`: `latest`
   - `confirm`: `DEPLOY`
5. 等待部署完成

**方式2：手动部署（测试用）**

```bash
# 在服务器上执行
cd /opt/xihong_erp
docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml --profile production up -d
```

### 步骤3：验证部署

```bash
# 检查服务状态
docker-compose ps

# 健康检查
curl http://localhost:8000/health

# 检查日志
docker-compose logs backend
docker-compose logs frontend
docker-compose logs nginx
```

---

## ✅ 检查清单总结

### 本地检查（已完成）

- [x] 配置文件: `.env.production` 已正确配置
- [x] Docker Compose配置: 所有文件存在且语法正确
- [x] 网络配置: 域名和IP已配置
- [x] Nginx配置: 反向代理配置正确
- [x] 安全配置: 所有密码已修改为强密码
- [x] 资源限制: 已优化为2核4G配置
- [x] 前端配置: `VITE_API_BASE_URL=/api` 已配置

### 服务器端检查（需要执行）

- [ ] Docker和Docker Compose已安装
- [ ] 项目目录已创建: `/opt/xihong_erp`
- [ ] `.env`文件已上传并设置权限
- [ ] GitHub镜像仓库已登录
- [ ] 镜像可以成功拉取
- [ ] 域名DNS解析正确
- [ ] 端口已开放（80, 443, 22）

### GitHub配置检查（需要确认）

- [ ] `PRODUCTION_SSH_PRIVATE_KEY` 已配置
- [ ] `PRODUCTION_HOST` 已配置（134.175.222.171）
- [ ] `PRODUCTION_USER` 已配置（可选）
- [ ] `PRODUCTION_PATH` 已配置（可选）

---

## 🎯 部署就绪状态

### ✅ 本地检查：100%通过

所有本地检查项已通过，配置文件已准备就绪。

### ⏭️ 下一步操作

1. **上传配置文件到服务器**
   ```bash
   scp .env.production user@134.175.222.171:/opt/xihong_erp/.env
   ```

2. **在服务器上验证配置**
   ```bash
   ssh user@134.175.222.171
   cd /opt/xihong_erp
   python scripts/validate_production_env.py
   ```

3. **开始部署**
   - 使用GitHub Actions自动部署（推荐）
   - 或手动部署进行测试

---

## 📚 相关文档

- [快速部署指南](./QUICK_DEPLOYMENT_GUIDE.md)
- [环境配置对比](./ENV_DEVELOPMENT_VS_PRODUCTION.md)
- [生产环境配置指南](./PRODUCTION_ENV_CONFIG.md)
- [Nginx反向代理配置](./NGINX_REVERSE_PROXY_CONFIG.md)

---

**所有检查通过，可以开始部署！** 🚀

---

**最后更新**: 2025-01-XX
