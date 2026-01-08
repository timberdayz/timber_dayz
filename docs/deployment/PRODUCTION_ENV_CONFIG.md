# 生产环境.env配置指南

**版本**: v4.19.7  
**适用**: 腾讯云2核4G Linux服务器  
**更新时间**: 2025-01-XX

---

## 📋 开发环境 vs 生产环境核心差异

### 1. 环境标识（必须修改）

| 配置项 | 开发环境 | 生产环境 | 说明 |
|--------|---------|---------|------|
| `ENVIRONMENT` | `development` | `production` | ⭐ 核心标识 |
| `APP_ENV` | `development` | `production` | 应用环境 |
| `DEBUG` | `false` | `false` | 必须关闭 |

### 2. 安全配置（必须修改）

| 配置项 | 开发环境 | 生产环境 | 说明 |
|--------|---------|---------|------|
| `POSTGRES_PASSWORD` | `erp_pass_2025` | `强随机密码24位+` | ⚠️ 必须修改 |
| `SECRET_KEY` | `默认值` | `32位随机字符串` | ⚠️ 必须修改 |
| `JWT_SECRET_KEY` | `默认值` | `32位随机字符串` | ⚠️ 必须修改 |
| `ACCOUNT_ENCRYPTION_KEY` | `空（自动生成）` | `Fernet密钥` | 建议设置 |
| `REDIS_PASSWORD` | `空` | `强随机密码16位+` | ⚠️ 必须修改 |

### 3. 网络配置（必须修改）

| 配置项 | 开发环境 | 生产环境 | 说明 |
|--------|---------|---------|------|
| `HOST` | `127.0.0.1` | `0.0.0.0` | 允许外部访问 |
| `ALLOWED_ORIGINS` | `http://localhost:...` | `http://your-server-ip` | 仅允许实际地址 |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | `your-server-ip` | 安全限制 |
| `VITE_API_URL` | `http://localhost:8001` | `http://your-server-ip:8000` | 前端API地址 |

### 4. 性能配置（2核4G优化）

| 配置项 | 开发环境 | 生产环境 | 说明 |
|--------|---------|---------|------|
| `DB_POOL_SIZE` | `20` | `10` | 资源优化 |
| `DB_MAX_OVERFLOW` | `40` | `20` | 资源优化 |
| `MAX_CONCURRENT_TASKS` | `3` | `2` | 资源优化 |

### 5. 功能配置

| 配置项 | 开发环境 | 生产环境 | 说明 |
|--------|---------|---------|------|
| `PLAYWRIGHT_HEADLESS` | `false` | `true` | 无头模式 |
| `VITE_MODE` | `development` | `production` | 构建模式 |
| `LOG_LEVEL` | `INFO` | `INFO` | 日志级别 |
| `DATABASE_ECHO` | `false` | `false` | 禁止SQL日志 |

---

## 🔧 生产环境.env配置模板

```bash
# =====================================================
# 生产环境配置（腾讯云2核4G服务器）
# =====================================================

# ==================== 环境标识 ====================
ENVIRONMENT=production
APP_ENV=production
DEBUG=false

# ==================== 数据库配置 ====================
# Docker容器内使用服务名 'postgres'
DATABASE_URL=postgresql://erp_user:你的强密码@postgres:5432/xihong_erp
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=erp_user
POSTGRES_PASSWORD=你的强密码_至少24位
POSTGRES_DB=xihong_erp

# ==================== 安全配置（必须修改） ====================
# 生成命令: python -c "import secrets; print(secrets.token_urlsafe(32))"
SECRET_KEY=你的32位随机字符串
JWT_SECRET_KEY=你的32位随机字符串

# 生成命令: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ACCOUNT_ENCRYPTION_KEY=你的Fernet密钥

# ==================== 服务器配置 ====================
HOST=0.0.0.0
PORT=8000
FRONTEND_PORT=80

# 根据实际情况修改（服务器IP或域名）
ALLOWED_ORIGINS=http://your-server-ip,https://your-domain.com
ALLOWED_HOSTS=your-server-ip,your-domain.com

# ==================== Redis配置 ====================
REDIS_URL=redis://:你的Redis密码@redis:6379/0
REDIS_PASSWORD=你的Redis密码_至少16位
CELERY_BROKER_URL=redis://:你的Redis密码@redis:6379/0
CELERY_RESULT_BACKEND=redis://:你的Redis密码@redis:6379/0

# ==================== 前端配置 ====================
# 根据实际情况修改（服务器IP或域名）
VITE_API_URL=http://your-server-ip:8000
VITE_MODE=production

# ==================== 性能优化（2核4G） ====================
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
MAX_CONCURRENT_TASKS=2

# ==================== Playwright配置 ====================
PLAYWRIGHT_HEADLESS=true
PLAYWRIGHT_SLOW_MO=0

# ==================== 日志配置 ====================
LOG_LEVEL=INFO
DATABASE_ECHO=false

# ==================== 其他配置 ====================
# 连接超时和回收
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800

# JWT Token配置
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
JWT_ALGORITHM=HS256

# 数据保留
DATA_RETENTION_DAYS=90
```

---

## 🚀 快速生成生产环境配置

### 方法1：使用检查工具生成密码

```bash
# 生成所有密码和密钥
python scripts/check_passwords_and_registry.py --generate
```

### 方法2：手动创建配置文件

```bash
# 1. 复制生产环境模板
cp env.production.example .env.production

# 2. 编辑配置文件
nano .env.production

# 3. 修改以下关键配置：
#    - ENVIRONMENT=production
#    - 所有密码（使用生成的强密码）
#    - 服务器IP地址
#    - 性能优化参数
```

---

## ⚠️ 重要注意事项

### 1. 密码安全
- ❌ **禁止**：使用默认密码（如`erp_pass_2025`）
- ❌ **禁止**：在代码中硬编码密码
- ✅ **必须**：使用强随机密码（至少24位）
- ✅ **必须**：定期更换密码

### 2. 网络安全
- ❌ **禁止**：`ALLOWED_ORIGINS=*`（允许所有来源）
- ✅ **必须**：仅允许实际域名或IP
- ✅ **建议**：使用HTTPS（配置SSL证书）

### 3. 资源优化
- ⚠️ **注意**：2核4G服务器必须使用`docker-compose.cloud.yml`
- ⚠️ **注意**：连接池大小需要根据服务器配置调整
- ✅ **建议**：监控资源使用，及时调整

### 4. 日志管理
- ❌ **禁止**：生产环境使用`DEBUG`级别
- ❌ **禁止**：生产环境开启`DATABASE_ECHO`
- ✅ **建议**：使用日志轮转和清理策略

---

## 📝 配置检查清单

### 部署前检查

- [ ] `ENVIRONMENT=production`
- [ ] `APP_ENV=production`
- [ ] `DEBUG=false`
- [ ] `POSTGRES_PASSWORD`已修改为强密码
- [ ] `SECRET_KEY`已修改为32位随机字符串
- [ ] `JWT_SECRET_KEY`已修改为32位随机字符串
- [ ] `ACCOUNT_ENCRYPTION_KEY`已设置
- [ ] `REDIS_PASSWORD`已修改为强密码
- [ ] `HOST=0.0.0.0`
- [ ] `ALLOWED_ORIGINS`已修改为服务器IP或域名
- [ ] `ALLOWED_HOSTS`已修改为服务器IP或域名
- [ ] `VITE_API_URL`已修改为服务器地址
- [ ] `VITE_MODE=production`
- [ ] `DB_POOL_SIZE=10`（2核4G优化）
- [ ] `DB_MAX_OVERFLOW=20`（2核4G优化）
- [ ] `PLAYWRIGHT_HEADLESS=true`
- [ ] `DATABASE_ECHO=false`

---

**最后更新**: 2025-01-XX
