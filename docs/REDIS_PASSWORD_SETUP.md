# Redis 密码配置指南

**版本**: v4.19.5  
**日期**: 2026-01-05

## 概述

系统已支持 Redis 密码认证，适用于生产环境部署。

## 配置方式

### 方式 1：使用 REDIS_URL（推荐）

直接设置完整的 Redis URL，包含密码：

```bash
# Windows PowerShell
$env:REDIS_URL="redis://:your_redis_password@localhost:6379/0"
$env:CELERY_BROKER_URL="redis://:your_redis_password@localhost:6379/0"
$env:CELERY_RESULT_BACKEND="redis://:your_redis_password@localhost:6379/0"

# Linux/Mac
export REDIS_URL="redis://:your_redis_password@localhost:6379/0"
export CELERY_BROKER_URL="redis://:your_redis_password@localhost:6379/0"
export CELERY_RESULT_BACKEND="redis://:your_redis_password@localhost:6379/0"
```

### 方式 2：使用独立配置项

如果未设置 `REDIS_URL`，系统会自动从以下环境变量构建：

```bash
# Windows PowerShell
$env:REDIS_HOST="localhost"
$env:REDIS_PORT="6379"
$env:REDIS_PASSWORD="your_redis_password"
$env:REDIS_DB="0"

# Linux/Mac
export REDIS_HOST="localhost"
export REDIS_PORT="6379"
export REDIS_PASSWORD="your_redis_password"
export REDIS_DB="0"
```

### 方式 3：使用 .env 文件

在项目根目录创建 `.env` 文件：

```env
# Redis配置（方式1：推荐）
REDIS_URL=redis://:your_redis_password@localhost:6379/0
CELERY_BROKER_URL=redis://:your_redis_password@localhost:6379/0
CELERY_RESULT_BACKEND=redis://:your_redis_password@localhost:6379/0

# 或者方式2：独立配置项
# REDIS_HOST=localhost
# REDIS_PORT=6379
# REDIS_PASSWORD=your_redis_password
# REDIS_DB=0
```

## Redis URL 格式说明

### 无密码格式
```
redis://host:port/db
```
示例：`redis://localhost:6379/0`

### 带密码格式
```
redis://:password@host:port/db
```
示例：`redis://:mypassword@localhost:6379/0`

**注意**：密码前的冒号 `:` 是必需的，即使没有用户名。

## 验证配置

### 1. 检查环境变量

```bash
# Windows PowerShell
echo $env:REDIS_URL

# Linux/Mac
echo $REDIS_URL
```

### 2. 测试 Redis 连接

```bash
# 使用 redis-cli 测试
redis-cli -h localhost -p 6379 -a your_redis_password ping
# 应该返回: PONG
```

### 3. 查看应用启动日志

启动应用后，查看日志中的 Redis 连接信息：

```
[OK] Redis缓存已启用: redis://:****@localhost:6379/0
[RateLimit] Redis 存储连接正常
```

## 生产环境配置

### Docker Redis 配置

```bash
# 启动带密码的 Redis
docker run -d \
  --name redis \
  -p 6379:6379 \
  redis:alpine \
  redis-server --requirepass your_redis_password
```

### 生产环境 .env 文件

参考 `config/production.example.env`：

```env
# Redis配置
REDIS_URL=redis://:CHANGE_THIS_PASSWORD@your_redis_host:6379/0
CELERY_BROKER_URL=redis://:CHANGE_THIS_PASSWORD@your_redis_host:6379/0
CELERY_RESULT_BACKEND=redis://:CHANGE_THIS_PASSWORD@your_redis_host:6379/0
```

**重要**：生产环境必须修改密码！

## 故障排查

### 问题 1：Authentication required 错误

**症状**：
```
[ERROR] [UserTaskQuota] 减少用户 X 任务计数失败: Authentication required.
```

**原因**：Redis 服务器启用了密码认证，但应用未配置密码。

**解决方案**：
1. 检查 `REDIS_URL` 环境变量是否包含密码
2. 确认 Redis 服务器密码是否正确
3. 重新启动应用

### 问题 2：Redis 连接失败

**症状**：
```
[WARNING] Redis连接失败，缓存未启用
```

**解决方案**：
1. 检查 Redis 服务是否运行
2. 检查网络连接
3. 检查防火墙设置
4. 验证 Redis URL 格式是否正确

### 问题 3：开发环境降级

**症状**：开发环境 Redis 不可用时，系统自动降级到内存存储。

**说明**：这是正常行为，不影响系统运行。生产环境会强制要求 Redis。

## 安全建议

1. **使用强密码**：至少 16 个字符，包含大小写字母、数字和特殊字符
2. **定期更换密码**：建议每 3 个月更换一次
3. **限制网络访问**：仅允许应用服务器访问 Redis
4. **使用 TLS**：生产环境建议启用 Redis TLS（需要额外配置）

## 相关文件

- `backend/utils/config.py` - Redis 配置读取
- `backend/celery_app.py` - Celery Redis 配置
- `backend/utils/redis_client.py` - Redis 客户端初始化
- `backend/services/cache_service.py` - 缓存服务
- `config/production.example.env` - 生产环境配置示例

