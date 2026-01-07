# 环境变量参考文档

版本: v4.19.7  
更新时间: 2026-01-05  
基于: `env.template`（Single Source of Truth）

## 概述

本文档提供西虹ERP系统所有环境变量的完整参考，包括：
- 优先级分类（P0/P1/P2）
- 功能分类（数据库/安全/性能等）
- 默认值和推荐值
- 依赖关系
- 使用示例

**重要提示**：
- 所有环境变量定义以 `env.template` 为准（SSOT）
- 使用 `scripts/generate-env-files.py` 生成不同环境的配置文件
- 使用 `scripts/validate-env.py` 验证配置完整性

---

## 优先级分类

### P0 - 必须配置（生产环境）

这些变量是系统运行的基础，缺失或错误会导致系统无法启动或存在安全风险。

| 变量名 | 说明 | 默认值 | 生产环境要求 |
|--------|------|--------|--------------|
| `ENVIRONMENT` | 运行环境 | `development` | 必须设置为 `production` |
| `DATABASE_URL` | 数据库连接字符串 | `postgresql://...` | 必须指向生产数据库 |
| `SECRET_KEY` | 应用密钥 | `xihong-erp-secret-key-2025` | ⚠️ 必须修改为强随机字符串 |
| `JWT_SECRET_KEY` | JWT 签名密钥 | `xihong-erp-jwt-secret-2025` | ⚠️ 必须修改为强随机字符串 |

**生成密钥命令**：
```bash
# SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"

# JWT_SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"

# ACCOUNT_ENCRYPTION_KEY (Fernet)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

### P1 - 建议配置

这些变量影响系统性能和功能完整性，建议配置。

#### 服务器配置

| 变量名 | 说明 | 默认值 | 推荐值（生产） |
|--------|------|--------|--------------|
| `HOST` | 服务器监听地址 | `127.0.0.1` | `0.0.0.0` |
| `PORT` | 后端 API 端口 | `8001` | `8001` |
| `FRONTEND_PORT` | 前端端口 | `5173` | `80` 或 `443` |
| `ALLOWED_ORIGINS` | CORS 允许来源 | `http://localhost:...` | 仅实际域名 |
| `ALLOWED_HOSTS` | 允许的主机 | `localhost,127.0.0.1` | 实际域名 |

#### 数据库连接池配置

| 变量名 | 说明 | 默认值 | 推荐值（生产） |
|--------|------|--------|--------------|
| `DB_POOL_SIZE` | 连接池大小 | `20` | `30-50` |
| `DB_MAX_OVERFLOW` | 连接池最大溢出 | `40` | `50-100` |
| `DB_POOL_TIMEOUT` | 连接超时（秒） | `60` | `30-60` |
| `DB_POOL_RECYCLE` | 连接回收时间（秒） | `1800` | `1800-3600` |
| `DATABASE_ECHO` | 显示 SQL 语句 | `false` | `false`（生产） |

#### Redis 配置

| 变量名 | 说明 | 默认值 | 推荐值（生产） |
|--------|------|--------|--------------|
| `REDIS_URL` | Redis 连接 URL | `redis://localhost:6379/0` | `redis://:password@redis:6379/0` |
| `REDIS_ENABLED` | 是否启用 Redis | `true` | `true`（生产必须） |

#### 执行器配置（v4.19.0 新增）

| 变量名 | 说明 | 默认值 | 推荐值（生产） |
|--------|------|--------|--------------|
| `CPU_EXECUTOR_WORKERS` | CPU 进程池工作线程数 | `max(1, CPU核心数-1)` | 手动设置（根据服务器配置） |
| `IO_EXECUTOR_WORKERS` | I/O 线程池工作线程数 | `min(CPU核心数*5, 20)` | 手动设置（根据服务器配置） |

#### JWT Token 配置

| 变量名 | 说明 | 默认值 | 推荐值（生产） |
|--------|------|--------|--------------|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access Token 过期时间（分钟） | `15` | `15-30` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh Token 过期时间（天） | `7` | `7-30` |

#### 日志配置

| 变量名 | 说明 | 默认值 | 推荐值（生产） |
|--------|------|--------|--------------|
| `LOG_LEVEL` | 日志级别 | `INFO` | `INFO` 或 `WARNING` |
| `LOG_FILE` | 日志文件路径 | `logs/backend.log` | `logs/backend.log` |

#### Playwright 配置

| 变量名 | 说明 | 默认值 | 推荐值（生产） |
|--------|------|--------|--------------|
| `PLAYWRIGHT_HEADLESS` | 是否无头模式 | `false` | `true`（生产必须） |
| `PLAYWRIGHT_SLOW_MO` | 慢速模式（毫秒） | `0` | `0`（生产） |
| `PLAYWRIGHT_TIMEOUT` | 超时（毫秒） | `30000` | `30000` |

---

### P2 - 可选配置

这些变量用于高级功能或优化，可根据需要配置。

#### pgAdmin 配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `PGADMIN_EMAIL` | pgAdmin 邮箱 | `admin@xihong.com` |
| `PGADMIN_PASSWORD` | pgAdmin 密码 | `admin` |

#### 邮件配置（告警通知）

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `SMTP_HOST` | SMTP 服务器地址 | `smtp.example.com` |
| `SMTP_PORT` | SMTP 端口 | `587` |
| `SMTP_USER` | SMTP 用户名 | `your-email@example.com` |
| `SMTP_PASSWORD` | SMTP 密码 | `your-password` |
| `SMTP_FROM` | 发件人邮箱 | `noreply@example.com` |

#### Metabase 配置（BI 功能）

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `METABASE_URL` | Metabase 服务地址 | `http://localhost:8080` |
| `METABASE_API_KEY` | Metabase API Key | （需从 Metabase 获取） |
| `METABASE_ENCRYPTION_SECRET_KEY` | Metabase 加密密钥 | （生产环境必须修改） |
| `METABASE_EMBEDDING_SECRET_KEY` | Metabase 嵌入密钥 | （生产环境必须修改） |

---

## 功能分类

### 数据库相关

- `DATABASE_URL`（P0）
- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`（P1）
- `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE`（P1）
- `DATABASE_ECHO`（P1）

### 安全相关

- `SECRET_KEY`（P0）
- `JWT_SECRET_KEY`（P0）
- `ACCOUNT_ENCRYPTION_KEY`（P0）
- `JWT_ALGORITHM`（P1）
- `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`（P1）

### 性能相关

- `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`（P1）
- `CPU_EXECUTOR_WORKERS`, `IO_EXECUTOR_WORKERS`（P1）
- `MAX_CONCURRENT_TASKS`（P1）

### 日志相关

- `LOG_LEVEL`（P1）
- `LOG_FILE`（P1）

### 第三方服务

- `REDIS_URL`, `REDIS_ENABLED`（P1）
- `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`（P1）
- `METABASE_URL`, `METABASE_API_KEY`（P2）
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`（P2）

---

## 依赖关系

### 数据库连接

如果设置了 `DATABASE_URL`，系统会优先使用它。否则，系统会使用 `POSTGRES_HOST`、`POSTGRES_PORT` 等独立配置构建连接字符串。

### Redis 连接

如果设置了 `REDIS_URL`，系统会优先使用它。否则，系统会使用 `REDIS_HOST`、`REDIS_PORT`、`REDIS_PASSWORD` 等独立配置构建连接 URL。

### Celery 配置

如果未设置 `CELERY_BROKER_URL` 和 `CELERY_RESULT_BACKEND`，系统会使用 `REDIS_URL`。

---

## 环境特定配置

### 开发环境

```bash
ENVIRONMENT=development
APP_ENV=development
DEBUG=true
HOST=127.0.0.1
POSTGRES_PORT_EXTERNAL=15432
DATABASE_ECHO=true
LOG_LEVEL=DEBUG
PLAYWRIGHT_HEADLESS=false
PLAYWRIGHT_SLOW_MO=100
REDIS_ENABLED=false
```

### 生产环境

```bash
ENVIRONMENT=production
APP_ENV=production
DEBUG=false
HOST=0.0.0.0
DATABASE_ECHO=false
LOG_LEVEL=INFO
PLAYWRIGHT_HEADLESS=true
PLAYWRIGHT_SLOW_MO=0
REDIS_ENABLED=true
```

---

## 使用示例

### 最小配置（开发环境）

```bash
# .env
ENVIRONMENT=development
DATABASE_URL=postgresql://erp_dev:dev_pass_2025@localhost:15432/xihong_erp_dev
SECRET_KEY=dev-secret-key-not-for-production
JWT_SECRET_KEY=dev-jwt-secret-not-for-production
```

### 完整配置（生产环境）

参考 `env.production.example` 文件。

---

## 验证和检查

### 使用验证脚本

```bash
# 基础验证（仅 P0）
python scripts/validate-env.py --env-file .env

# 严格验证（P0 + P1）
python scripts/validate-env.py --env-file .env --strict

# JSON 输出（用于脚本消费）
python scripts/validate-env.py --env-file .env --json
```

### 生产环境检查清单

- [ ] `ENVIRONMENT=production`
- [ ] `SECRET_KEY` 已修改（不是默认值）
- [ ] `JWT_SECRET_KEY` 已修改（不是默认值）
- [ ] `POSTGRES_PASSWORD` 已修改（不是默认值）
- [ ] `DATABASE_URL` 指向正确的生产数据库
- [ ] `REDIS_ENABLED=true`（如果使用 Celery）
- [ ] `PLAYWRIGHT_HEADLESS=true`
- [ ] `ALLOWED_ORIGINS` 仅包含实际域名
- [ ] `LOG_LEVEL=INFO` 或 `WARNING`
- [ ] `DATABASE_ECHO=false`

---

## 相关文档

- [云端部署环境变量配置清单](./CLOUD_ENVIRONMENT_VARIABLES.md)
- [Docker 部署指南](./DOCKER_STARTUP_GUIDE.md)
- [安全配置指南](./security_configuration.md)

---

## 更新历史

- **v4.19.7** (2026-01-05): 创建统一参考文档，基于 `env.template`（SSOT）
- **v4.19.0**: 新增执行器配置（`CPU_EXECUTOR_WORKERS`, `IO_EXECUTOR_WORKERS`）
- **v4.18.0**: 初始版本

