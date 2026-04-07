# 开发环境 vs 生产环境配置对比

**版本**: v4.19.7  
**更新时间**: 2025-01-XX

---

## 📊 核心差异总结

| 配置项 | 开发环境 | 生产环境 | 说明 |
|--------|---------|---------|------|
| **ENVIRONMENT** | `development` | `production` | ⭐ 核心标识 |
| **DEBUG** | `false` | `false` | 生产环境必须关闭 |
| **APP_ENV** | `development` | `production` | 应用环境标识 |
| **HOST** | `127.0.0.1` | `0.0.0.0` | 生产环境允许外部访问 |
| **ALLOWED_ORIGINS** | `http://localhost:...` | `https://your-domain.com` | 生产环境仅允许实际域名 |
| **ALLOWED_HOSTS** | `localhost,127.0.0.1` | `your-domain.com,server-ip` | 生产环境安全限制 |
| **LOG_LEVEL** | `INFO` | `INFO` 或 `WARNING` | 生产环境减少日志量 |
| **DATABASE_ECHO** | `false` | `false` | 生产环境禁止SQL日志 |
| **PLAYWRIGHT_HEADLESS** | `false` | `true` | 生产环境无头模式 |
| **VITE_MODE** | `development` | `production` | 前端构建模式 |
| **VITE_API_URL** | `http://localhost:8001` | `https://your-domain.com/api` | 前端API地址 |
| **DB_POOL_SIZE** | `20` | `10` (2核4G优化) | 生产环境资源优化 |
| **DB_MAX_OVERFLOW** | `40` | `20` (2核4G优化) | 生产环境资源优化 |

---

## 🔐 安全配置差异

### 开发环境（本地）
```bash
# 使用默认密码（仅开发）
POSTGRES_PASSWORD=erp_pass_2025
SECRET_KEY=xihong-erp-secret-key-2025
JWT_SECRET_KEY=xihong-erp-jwt-secret-2025
ACCOUNT_ENCRYPTION_KEY=  # 可选，自动生成
```

### 生产环境（服务器）
```bash
# ⚠️ 必须使用强随机密码
POSTGRES_PASSWORD=你的强随机密码_至少24位
SECRET_KEY=你的32位随机字符串
JWT_SECRET_KEY=你的32位随机字符串
ACCOUNT_ENCRYPTION_KEY=你的Fernet密钥  # 必须设置，避免重启后变化
REDIS_PASSWORD=你的强随机密码_至少16位
```

**生成命令**：
```bash
python scripts/check_passwords_and_registry.py --generate
```

---

## 🌐 网络配置差异

### 开发环境
```bash
# 本地开发，允许localhost多个端口
HOST=127.0.0.1
PORT=8001
FRONTEND_PORT=5173
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173
ALLOWED_HOSTS=localhost,127.0.0.1
VITE_API_URL=http://localhost:8001
```

### 生产环境
```bash
# 服务器部署，允许外部访问
HOST=0.0.0.0
PORT=8000  # 或8001，根据docker-compose配置
FRONTEND_PORT=80  # 或443（HTTPS）
ALLOWED_ORIGINS=https://your-domain.com,http://your-server-ip
ALLOWED_HOSTS=your-domain.com,your-server-ip
VITE_API_URL=https://your-domain.com/api  # 或 http://your-server-ip:8000
```

---

## 🗄️ 数据库配置差异

### 开发环境
```bash
# 本地Docker或本地PostgreSQL
DATABASE_URL=postgresql://erp_user:erp_pass_2025@postgres:5432/xihong_erp
# 或
DATABASE_URL=postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp
POSTGRES_PORT_EXTERNAL=15432  # Windows避免端口冲突
```

### 生产环境
```bash
# Docker容器内使用服务名
DATABASE_URL=postgresql://erp_user:你的强密码@postgres:5432/xihong_erp
POSTGRES_PORT_EXTERNAL=5432  # 或15432（如果外部访问）
```

---

## ⚡ 性能配置差异（2核4G服务器优化）

### 开发环境
```bash
# 开发环境可以使用更多资源
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=40
MAX_CONCURRENT_TASKS=3
```

### 生产环境（2核4G优化）
```bash
# 生产环境需要资源优化
DB_POOL_SIZE=10          # 从20降到10
DB_MAX_OVERFLOW=20       # 从40降到20
MAX_CONCURRENT_TASKS=2   # 从3降到2（根据实际情况调整）
```

---

## 🎭 Playwright配置差异

### 开发环境
```bash
# 开发环境可以看到浏览器操作
PLAYWRIGHT_HEADLESS=false
PLAYWRIGHT_SLOW_MO=100  # 慢速模式，便于观察
```

### 生产环境
```bash
# 生产环境无头模式，最快速度
PLAYWRIGHT_HEADLESS=true
PLAYWRIGHT_SLOW_MO=0
```

---

## 📦 前端构建差异

### 开发环境
```bash
# 开发模式，热重载
VITE_MODE=development
VITE_API_URL=http://localhost:8001
```

### 生产环境
```bash
# 生产模式，代码压缩和优化
VITE_MODE=production
VITE_API_URL=https://your-domain.com/api  # 或 http://your-server-ip:8000
```

---

## 🔍 日志配置差异

### 开发环境
```bash
# 开发环境可以输出更多日志
LOG_LEVEL=INFO  # 或 DEBUG
DATABASE_ECHO=false  # 可以设置为true查看SQL
```

### 生产环境
```bash
# 生产环境减少日志量
LOG_LEVEL=INFO  # 或 WARNING（减少日志量）
DATABASE_ECHO=false  # 必须关闭，避免性能问题
```

---

## 📋 完整配置对比表

### P0级别（必须配置）

| 配置项 | 开发环境值 | 生产环境值 | 差异说明 |
|--------|-----------|-----------|---------|
| `ENVIRONMENT` | `development` | `production` | ⭐ 核心差异 |
| `APP_ENV` | `development` | `production` | 应用环境 |
| `DEBUG` | `false` | `false` | 必须关闭 |
| `POSTGRES_PASSWORD` | `erp_pass_2025` | `强随机密码` | ⚠️ 必须修改 |
| `SECRET_KEY` | `默认值` | `强随机字符串` | ⚠️ 必须修改 |
| `JWT_SECRET_KEY` | `默认值` | `强随机字符串` | ⚠️ 必须修改 |
| `ACCOUNT_ENCRYPTION_KEY` | `空（自动生成）` | `Fernet密钥` | 建议设置 |

### P1级别（建议配置）

| 配置项 | 开发环境值 | 生产环境值 | 差异说明 |
|--------|-----------|-----------|---------|
| `HOST` | `127.0.0.1` | `0.0.0.0` | 允许外部访问 |
| `ALLOWED_ORIGINS` | `localhost:...` | `实际域名` | 安全限制 |
| `ALLOWED_HOSTS` | `localhost` | `域名+IP` | 安全限制 |
| `VITE_API_URL` | `http://localhost:8001` | `https://域名/api` | 前端API地址 |
| `VITE_MODE` | `development` | `production` | 构建模式 |
| `LOG_LEVEL` | `INFO` | `INFO/WARNING` | 日志级别 |
| `DB_POOL_SIZE` | `20` | `10` | 资源优化 |
| `DB_MAX_OVERFLOW` | `40` | `20` | 资源优化 |
| `PLAYWRIGHT_HEADLESS` | `false` | `true` | 无头模式 |
| `REDIS_PASSWORD` | `空` | `强随机密码` | 安全要求 |

---

## 🚀 生产环境配置生成

### 方法1：使用检查工具生成
```bash
python scripts/check_passwords_and_registry.py --generate
```

### 方法2：手动创建
```bash
# 1. 复制生产环境模板
cp env.production.example .env.production

# 2. 编辑配置文件
nano .env.production

# 3. 修改所有密码和密钥
# 4. 修改服务器地址和域名
# 5. 优化资源配置（2核4G）
```

---

## ⚠️ 重要注意事项

### 1. 密码安全
- ❌ **禁止**：使用默认密码
- ❌ **禁止**：在代码中硬编码密码
- ✅ **必须**：使用强随机密码（至少24位）
- ✅ **必须**：定期更换密码

### 2. 网络安全
- ❌ **禁止**：生产环境允许所有来源（`ALLOWED_ORIGINS=*`）
- ✅ **必须**：仅允许实际域名
- ✅ **建议**：使用HTTPS（配置SSL证书）

### 3. 资源优化
- ⚠️ **注意**：2核4G服务器需要降低资源限制
- ⚠️ **注意**：连接池大小需要根据服务器配置调整
- ✅ **建议**：使用`docker-compose.cloud.yml`优化配置

### 4. 日志管理
- ❌ **禁止**：生产环境使用`DEBUG`级别
- ❌ **禁止**：生产环境开启`DATABASE_ECHO`
- ✅ **建议**：使用日志轮转和清理策略

---

## 📝 生产环境.env配置示例

```bash
# =====================================================
# 生产环境配置（腾讯云2核4G服务器）
# =====================================================

# 环境标识
ENVIRONMENT=production
APP_ENV=production
DEBUG=false

# 数据库配置（Docker容器内）
DATABASE_URL=postgresql://erp_user:你的强密码@postgres:5432/xihong_erp
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=erp_user
POSTGRES_PASSWORD=你的强密码
POSTGRES_DB=xihong_erp

# 安全配置（必须修改）
SECRET_KEY=你的32位随机字符串
JWT_SECRET_KEY=你的32位随机字符串
ACCOUNT_ENCRYPTION_KEY=你的Fernet密钥

# 服务器配置
HOST=0.0.0.0
PORT=8000
FRONTEND_PORT=80
ALLOWED_ORIGINS=http://your-server-ip,https://your-domain.com
ALLOWED_HOSTS=your-server-ip,your-domain.com

# Redis配置
REDIS_URL=redis://:你的Redis密码@redis:6379/0
REDIS_PASSWORD=你的Redis密码
CELERY_BROKER_URL=redis://:你的Redis密码@redis:6379/0
CELERY_RESULT_BACKEND=redis://:你的Redis密码@redis:6379/0

# 前端配置
VITE_API_URL=http://your-server-ip:8000
VITE_MODE=production

# 性能优化（2核4G）
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
MAX_CONCURRENT_TASKS=2

# Playwright配置
PLAYWRIGHT_HEADLESS=true
PLAYWRIGHT_SLOW_MO=0

# 日志配置
LOG_LEVEL=INFO
DATABASE_ECHO=false
```

---

## 🔄 配置迁移检查清单

### 从开发环境迁移到生产环境

- [ ] 修改`ENVIRONMENT=production`
- [ ] 修改`APP_ENV=production`
- [ ] 修改`DEBUG=false`
- [ ] 生成并设置所有强密码（POSTGRES_PASSWORD, REDIS_PASSWORD）
- [ ] 生成并设置所有密钥（SECRET_KEY, JWT_SECRET_KEY, ACCOUNT_ENCRYPTION_KEY）
- [ ] 修改`HOST=0.0.0.0`
- [ ] 修改`ALLOWED_ORIGINS`为实际域名
- [ ] 修改`ALLOWED_HOSTS`为实际域名和IP
- [ ] 修改`VITE_API_URL`为服务器地址
- [ ] 修改`VITE_MODE=production`
- [ ] 优化资源配置（DB_POOL_SIZE, DB_MAX_OVERFLOW）
- [ ] 设置`PLAYWRIGHT_HEADLESS=true`
- [ ] 确认`DATABASE_ECHO=false`
- [ ] 确认`LOG_LEVEL=INFO`或`WARNING`

---

**最后更新**: 2025-01-XX
