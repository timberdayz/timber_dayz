# 云端部署环境变量配置清单

版本: v4.19.7  
更新时间: 2026-01-05

> **重要提示**：
> - 所有环境变量定义以 `env.template` 为准（Single Source of Truth）
> - 使用 `scripts/generate-env-files.py` 生成不同环境的配置文件
> - 使用 `scripts/validate-env.py` 验证配置完整性
> - 详细参考文档：参见 [环境变量参考文档](./ENVIRONMENT_VARIABLES_REFERENCE.md)

## 📋 必需环境变量（P0 - 必须配置）

### 1. 项目路径配置

| 变量名 | 说明 | 示例值 | 默认值 |
|--------|------|--------|--------|
| `PROJECT_ROOT` | 项目根目录绝对路径 | `/app` | 当前目录（自动检测） |
| `DATA_DIR` | 数据存储目录 | `/app/data` | `{PROJECT_ROOT}/data` |
| `DOWNLOADS_DIR` | 下载文件目录 | `/app/downloads` | `{PROJECT_ROOT}/downloads` |
| `TEMP_DIR` | 临时文件目录 | `/app/temp` | `{PROJECT_ROOT}/temp` |

**用途**: 支持云端部署时的灵活路径配置，避免硬编码路径问题

**验证命令**:
```bash
echo $PROJECT_ROOT
echo $DATA_DIR
python -c "from modules.core.path_manager import get_project_root; print(get_project_root())"
```

---

### 2. 数据库配置

| 变量名 | 说明 | 示例值 | 默认值 |
|--------|------|--------|--------|
| `DATABASE_URL` | PostgreSQL连接字符串 | `postgresql://user:pass@host:5432/db` | `postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp` |
| `POSTGRES_HOST` | PostgreSQL主机地址 | `postgres` | `localhost` |
| `POSTGRES_PORT` | PostgreSQL端口 | `5432` | `15432` |
| `POSTGRES_USER` | 数据库用户名 | `erp_user` | `erp_user` |
| `POSTGRES_PASSWORD` | 数据库密码 | `your-secure-password` | `erp_pass_2025` |
| `POSTGRES_DB` | 数据库名称 | `xihong_erp` | `xihong_erp` |

**生产环境要求**: 
- ✅ 必须使用强密码（至少16字符，包含大小写字母、数字、特殊符号）
- ✅ 不要使用默认密码
- ✅ 建议使用云数据库服务（RDS/Cloud SQL）

---

### 3. 安全配置（⭐ 必须修改）

| 变量名 | 说明 | 示例值 | 默认值 |
|--------|------|--------|--------|
| `SECRET_KEY` | 应用密钥 | `your-random-secret-key-here` | `xihong-erp-secret-key-2025` |
| `JWT_SECRET_KEY` | JWT签名密钥 | `your-jwt-secret-key-here` | `xihong-erp-jwt-secret-2025` |
| `ACCOUNT_ENCRYPTION_KEY` | 账号加密密钥 | `fernet-key-base64-encoded` | 自动生成 |

**🚨 生产环境强制要求**:
```python
# backend/utils/config.py 会在生产环境检查
if ENVIRONMENT == "production":
    if SECRET_KEY == "xihong-erp-secret-key-2025":
        raise RuntimeError("生产环境禁止使用默认SECRET密钥！")
```

**生成密钥命令**:
```bash
# 生成 SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"

# 生成 JWT_SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"

# 生成 ACCOUNT_ENCRYPTION_KEY (Fernet)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

### 4. 环境模式配置

| 变量名 | 说明 | 可选值 | 默认值 |
|--------|------|--------|--------|
| `ENVIRONMENT` | 运行环境 | `development` / `production` | `development` |
| `PLAYWRIGHT_HEADLESS` | 浏览器无头模式 | `true` / `false` | `false` |
| `PLAYWRIGHT_SLOW_MO` | 浏览器慢速模式（毫秒） | `0` - `1000` | `0` |

**环境配置说明**:
- **开发环境** (`ENVIRONMENT=development`):
  - 浏览器默认有头模式（headless=false, slow_mo=100）
  - 详细日志输出
  - 使用默认密钥（仅开发环境）
  
- **生产环境** (`ENVIRONMENT=production`):
  - 浏览器强制无头模式（headless=true, slow_mo=0）
  - 必须使用自定义密钥（强制检查）
  - 添加安全启动参数（--no-sandbox, --disable-dev-shm-usage）

---

## 📦 可选环境变量（P1 - 建议配置）

### 5. 性能配置

| 变量名 | 说明 | 默认值 | 推荐值（生产） |
|--------|------|--------|--------------|
| `DB_POOL_SIZE` | 数据库连接池大小 | `30` | `30-50` |
| `DB_MAX_OVERFLOW` | 连接池最大溢出 | `70` | `50-100` |
| `DB_POOL_TIMEOUT` | 连接超时（秒） | `60` | `30-60` |
| `DB_POOL_RECYCLE` | 连接回收时间（秒） | `1800` | `1800-3600` |

---

### 6. 采集任务配置

| 变量名 | 说明 | 默认值 | 推荐值 |
|--------|------|--------|--------|
| `MAX_COLLECTION_TASKS` | 最大并发采集任务数 | `3` | `3-5` |
| `COMPONENT_TIMEOUT` | 单组件超时（秒） | `300` | `300-600` |
| `TASK_TIMEOUT` | 单任务总超时（秒） | `1800` | `1800-3600` |
| `DOWNLOAD_TIMEOUT` | 文件下载超时（秒） | `120` | `120-300` |
| `DOWNLOADS_RETENTION_DAYS` | 下载文件保留天数 | `7` | `7-14` |
| `SCREENSHOTS_RETENTION_DAYS` | 截图文件保留天数 | `30` | `30-60` |

---

### 7. JWT配置

| 变量名 | 说明 | 默认值 | 推荐值 |
|--------|------|--------|--------|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access Token过期时间（分钟） | `60` | `60`（1小时） |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh Token过期时间（天） | `7` | `7-30` |

---

### 8. 服务端口配置

| 变量名 | 说明 | 默认值 | 云端建议 |
|--------|------|--------|----------|
| `HOST` | 后端服务监听地址 | `127.0.0.1` | `0.0.0.0` |
| `PORT` | 后端服务端口 | `8001` | `8001` |

**云端注意**: 
- 使用 `HOST=0.0.0.0` 允许外部访问
- 通过Nginx反向代理或云负载均衡器暴露服务

---

### 9. 日志配置

| 变量名 | 说明 | 默认值 | 生产建议 |
|--------|------|--------|----------|
| `LOG_LEVEL` | 日志级别 | `INFO` | `INFO` / `WARNING` |
| `DATABASE_ECHO` | 数据库SQL日志 | `false` | `false` |

---

## 🐳 Docker部署示例配置

### docker-compose.yml 环境变量配置

```yaml
version: '3.8'

services:
  backend:
    image: xihong-erp-backend:latest
    environment:
      # 环境模式
      - ENVIRONMENT=production
      
      # 路径配置（Docker容器内路径）
      - PROJECT_ROOT=/app
      - DATA_DIR=/app/data
      - DOWNLOADS_DIR=/app/downloads
      - TEMP_DIR=/app/temp
      
      # 数据库配置
      - DATABASE_URL=postgresql://erp_user:${DB_PASSWORD}@postgres:5432/xihong_erp
      - POSTGRES_HOST=postgres
      - POSTGRES_PORT=5432
      - POSTGRES_USER=erp_user
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=xihong_erp
      
      # 安全配置（从.env文件或Docker Secrets读取）
      - SECRET_KEY=${SECRET_KEY}
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - ACCOUNT_ENCRYPTION_KEY=${ACCOUNT_ENCRYPTION_KEY}
      
      # Playwright配置
      - PLAYWRIGHT_HEADLESS=true
      - PLAYWRIGHT_SLOW_MO=0
      
      # 采集任务配置
      - MAX_COLLECTION_TASKS=3
      - COMPONENT_TIMEOUT=600
      - TASK_TIMEOUT=3600
      
      # 服务配置
      - HOST=0.0.0.0
      - PORT=8001
      
    volumes:
      - ./data:/app/data
      - ./downloads:/app/downloads
      - ./temp:/app/temp
      - ./config:/app/config
      - ./profiles:/app/profiles  # Playwright浏览器配置
    
    ports:
      - "8001:8001"
    
    depends_on:
      - postgres
  
  postgres:
    image: postgres:15
    environment:
      - POSTGRES_USER=erp_user
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=xihong_erp
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "15432:5432"

volumes:
  postgres_data:
```

---

## 🔐 敏感信息管理

### 方式1: .env文件（开发环境）

```bash
# .env.production
ENVIRONMENT=production
SECRET_KEY=your-random-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-key-here
ACCOUNT_ENCRYPTION_KEY=fernet-key-base64-encoded
DB_PASSWORD=your-secure-db-password
```

**使用**:
```bash
docker-compose --env-file .env.production up -d
```

---

### 方式2: Docker Secrets（生产推荐）

```yaml
services:
  backend:
    secrets:
      - secret_key
      - jwt_secret_key
      - db_password
    environment:
      - SECRET_KEY_FILE=/run/secrets/secret_key
      - JWT_SECRET_KEY_FILE=/run/secrets/jwt_secret_key
      - DB_PASSWORD_FILE=/run/secrets/db_password

secrets:
  secret_key:
    external: true
  jwt_secret_key:
    external: true
  db_password:
    external: true
```

**创建Secret**:
```bash
echo "your-random-secret-key" | docker secret create secret_key -
echo "your-jwt-secret-key" | docker secret create jwt_secret_key -
echo "your-db-password" | docker secret create db_password -
```

---

### 方式3: 云服务环境变量（云平台）

**AWS ECS**:
```json
{
  "containerDefinitions": [{
    "environment": [
      {"name": "ENVIRONMENT", "value": "production"},
      {"name": "PROJECT_ROOT", "value": "/app"}
    ],
    "secrets": [
      {"name": "SECRET_KEY", "valueFrom": "arn:aws:secretsmanager:..."},
      {"name": "DB_PASSWORD", "valueFrom": "arn:aws:secretsmanager:..."}
    ]
  }]
}
```

**Kubernetes ConfigMap + Secret**:
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: xihong-erp-config
data:
  ENVIRONMENT: "production"
  PROJECT_ROOT: "/app"
  PLAYWRIGHT_HEADLESS: "true"
---
apiVersion: v1
kind: Secret
metadata:
  name: xihong-erp-secrets
type: Opaque
data:
  SECRET_KEY: <base64-encoded>
  JWT_SECRET_KEY: <base64-encoded>
  DB_PASSWORD: <base64-encoded>
```

---

## ✅ 配置验证清单

### 启动前验证

- [ ] 所有P0级别环境变量已配置
- [ ] 生产环境已修改默认密钥
- [ ] 数据库连接字符串正确
- [ ] 路径目录存在且有写入权限
- [ ] Playwright浏览器已安装（`playwright install chromium`）

### 运行时验证

```bash
# 验证环境变量加载
python -c "
import os
from backend.utils.config import get_settings
settings = get_settings()
print(f'ENVIRONMENT: {settings.ENVIRONMENT}')
print(f'DATABASE_URL: {settings.DATABASE_URL[:30]}...')
print(f'PLAYWRIGHT_HEADLESS: {settings.PLAYWRIGHT_HEADLESS}')
"

# 验证数据库连接
python -c "
from backend.models.database import engine
from sqlalchemy import text
with engine.connect() as conn:
    result = conn.execute(text('SELECT version()'))
    print('PostgreSQL:', result.scalar())
"

# 验证路径配置
python -c "
from modules.core.path_manager import (
    get_project_root, get_data_dir, 
    get_downloads_dir, get_temp_dir
)
print('PROJECT_ROOT:', get_project_root())
print('DATA_DIR:', get_data_dir())
print('DOWNLOADS_DIR:', get_downloads_dir())
print('TEMP_DIR:', get_temp_dir())
"

# 验证Playwright安装
python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    print('Chromium:', p.chromium.executable_path)
"
```

---

## 🚀 快速部署配置模板

### 最小配置（开发测试）

```bash
# .env.dev
ENVIRONMENT=development
DATABASE_URL=postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp
```

### 完整配置（生产环境）

```bash
# .env.production
# 环境模式
ENVIRONMENT=production

# 路径配置
PROJECT_ROOT=/app
DATA_DIR=/app/data
DOWNLOADS_DIR=/app/downloads
TEMP_DIR=/app/temp

# 数据库配置
DATABASE_URL=postgresql://erp_user:${DB_PASSWORD}@postgres:5432/xihong_erp
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=erp_user
POSTGRES_PASSWORD=${DB_PASSWORD}
POSTGRES_DB=xihong_erp

# 数据库连接池配置
DB_POOL_SIZE=30
DB_MAX_OVERFLOW=70
DB_POOL_TIMEOUT=60
DB_POOL_RECYCLE=1800

# 安全配置（必须修改）
SECRET_KEY=${SECRET_KEY}
JWT_SECRET_KEY=${JWT_SECRET_KEY}
ACCOUNT_ENCRYPTION_KEY=${ACCOUNT_ENCRYPTION_KEY}
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# Playwright配置
PLAYWRIGHT_HEADLESS=true
PLAYWRIGHT_SLOW_MO=0

# 采集任务配置
MAX_COLLECTION_TASKS=3
COMPONENT_TIMEOUT=600
TASK_TIMEOUT=3600
DOWNLOAD_TIMEOUT=300
DOWNLOADS_RETENTION_DAYS=7
SCREENSHOTS_RETENTION_DAYS=30

# 服务配置
HOST=0.0.0.0
PORT=8001
LOG_LEVEL=INFO
DATABASE_ECHO=false

# 可选：Redis配置
# REDIS_URL=redis://redis:6379/0

# 可选：代理配置
# PROXY_MODE=none
# PROXY_HOST=
# PROXY_PORT=
```

---

## 🔧 故障排查

### 问题1: 数据库连接失败

**症状**: `FATAL: password authentication failed`

**检查**:
```bash
# 验证环境变量
echo $DATABASE_URL
echo $POSTGRES_PASSWORD

# 测试连接
psql $DATABASE_URL
```

**解决**:
- 确认密码正确
- 确认PostgreSQL已启动
- 确认端口映射正确（Docker）

---

### 问题2: 浏览器无法启动

**症状**: `Executable doesn't exist at /path/to/chromium`

**检查**:
```bash
# 验证Playwright安装
playwright install chromium
playwright install-deps  # 安装系统依赖
```

**Docker解决**:
```dockerfile
# Dockerfile中添加
FROM mcr.microsoft.com/playwright/python:v1.40.0-focal
RUN playwright install chromium
RUN playwright install-deps
```

---

### 问题3: 路径权限问题

**症状**: `Permission denied: '/app/data'`

**检查**:
```bash
ls -la /app
```

**解决**:
```bash
# 修改目录权限
chown -R appuser:appuser /app/data /app/downloads /app/temp

# 或在Dockerfile中
RUN mkdir -p /app/data /app/downloads /app/temp && \
    chown -R appuser:appuser /app
```

---

### 问题4: 生产环境使用默认密钥

**症状**: `RuntimeError: 生产环境禁止使用默认JWT密钥！`

**解决**:
```bash
# 生成新密钥
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
export JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# 添加到.env文件
echo "SECRET_KEY=$SECRET_KEY" >> .env.production
echo "JWT_SECRET_KEY=$JWT_SECRET_KEY" >> .env.production
```

---

## 📝 检查清单

### 部署前检查

- [ ] 所有P0级别环境变量已配置
- [ ] 生产环境SECRET_KEY和JWT_SECRET_KEY已修改
- [ ] DATABASE_URL指向正确的数据库
- [ ] ENVIRONMENT设置为production
- [ ] PLAYWRIGHT_HEADLESS设置为true
- [ ] 路径目录已创建且有权限
- [ ] Playwright浏览器已安装

### 部署后验证

- [ ] 后端服务正常启动（`http://your-domain:8001/api/docs`可访问）
- [ ] 数据库连接成功（查看启动日志）
- [ ] APScheduler初始化成功（查看启动日志）
- [ ] 前端可以访问后端API
- [ ] 采集任务可以创建和执行
- [ ] 无头浏览器模式正常工作

---

## 📚 相关文档

- [项目根目录管理](../guides/path_management.md)
- [Docker部署指南](./docker_deployment.md)
- [安全配置指南](./security_configuration.md)
- [故障排查手册](./troubleshooting.md)

---

## 🎯 总结

**最小配置**（开发）: 2个变量
```
ENVIRONMENT=development
DATABASE_URL=...
```

**完整配置**（生产）: 20+个变量
- 路径配置（4个）
- 数据库配置（6个）
- 安全配置（3个）⭐
- 环境配置（3个）
- 性能配置（4个）
- 其他配置（6+个）

**关键原则**:
1. ⭐ 生产环境必须修改所有默认密钥
2. ⭐ 使用环境变量而非硬编码路径
3. ⭐ 敏感信息使用Docker Secrets或云服务密钥管理
4. ⭐ 定期轮换密钥（每90天）
