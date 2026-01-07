# 系统启动指南

**版本**: v4.6.3  
**最后更新**: 2025-11-05

---

## 🚀 推荐启动方式

### 方式1：完整启动（生产环境 + 高性能开发）⭐⭐⭐

**特点**：
- ✅ Redis缓存加速（95%性能提升）
- ✅ 完整功能体验
- ✅ 适合生产环境和性能测试

**命令**：
```bash
# 使用启动脚本（推荐）
start_system_with_redis.bat

# 或手动启动
docker-compose up -d postgres
docker run -d -p 6379:6379 --name xihong_erp_redis redis:alpine
python run.py
```

**预期日志**：
```
[OK] PostgreSQL PATH配置完成
[OK] 数据库连接验证成功
[OK] API速率限制已启用
[OK] Redis缓存已启用  ⬅️ 关键标志
总启动时间: 0.57秒
```

---

### 方式2：快速启动（日常开发）⭐⭐

**特点**：
- ✅ 启动快速
- ✅ 功能完整（无缓存但不影响）
- ✅ 数据实时（便于调试）

**命令**：
```bash
# 使用快速脚本（推荐）
start_system_quick.bat

# 或手动启动
docker-compose up -d postgres
python run.py
```

**预期日志**：
```
[OK] 数据库连接验证成功
[SKIP] Redis缓存未启用  ⬅️ 正常，开发环境可选
总启动时间: 0.57秒
```

---

### 方式3：Docker完整启动（一键部署）

**特点**：
- ✅ 一条命令启动所有服务
- ✅ 适合生产环境部署
- ✅ 服务隔离和管理

**命令**：
```bash
docker-compose up -d
```

**启动的服务**：
- PostgreSQL（端口5432）
- Redis（端口6379）
- 后端API（端口8001）
- 前端界面（端口5173）

---

## 🔍 启动验证清单

### 检查服务状态

```bash
# 1. 检查Docker容器
docker ps

# 应该看到：
# xihong_erp_postgres  (healthy)
# xihong_erp_redis     (if started)

# 2. 检查端口占用
netstat -ano | findstr "5432 6379 8001 5173"

# 应该看到：
# 5432 - PostgreSQL
# 6379 - Redis (if started)
# 8001 - 后端API
# 5173 - 前端

# 3. 测试API
curl http://localhost:8001/health
# 应该返回：{"status": "healthy"}

# 4. 访问前端
# 浏览器打开：http://localhost:5173
# 应该看到：业务概览页面
```

---

## ⚙️ 环境配置

### 开发环境（默认）

```bash
# 不需要设置环境变量
# 使用默认配置：
# - ENVIRONMENT=development
# - 默认JWT密钥（会有警告）
# - Redis可选

# 启动
python run.py
```

### 生产环境（必须配置）

```bash
# 必须设置环境变量
export ENVIRONMENT=production
export JWT_SECRET_KEY="至少32字符的随机密钥"
export SECRET_KEY="另一个32字符的随机密钥"

# 推荐设置
export RATE_LIMIT_ENABLED=true
export REDIS_URL="redis://localhost:6379/0"
export DATABASE_URL="postgresql://user:pass@host:5432/db"

# 启动
python run.py
```

### 环境变量生成

**生成安全的密钥**：
```python
import secrets

# 生成JWT密钥
jwt_key = secrets.token_urlsafe(32)
print(f"JWT_SECRET_KEY={jwt_key}")

# 生成SECRET密钥
secret_key = secrets.token_urlsafe(32)
print(f"SECRET_KEY={secret_key}")
```

---

## 🐛 常见问题

### Q1: Redis连接失败怎么办？

**现象**：
```
[SKIP] Redis缓存未启用: Connection refused
```

**解决方案**：
```bash
# 检查Redis是否运行
docker ps | findstr redis

# 如果没有运行，启动它
docker start xihong_erp_redis
# 或
docker run -d -p 6379:6379 --name xihong_erp_redis redis:alpine

# 重启ERP系统
python run.py
```

**说明**：这不是错误，系统会自动降级，功能正常

---

### Q2: 生产环境启动失败？

**现象**：
```
RuntimeError: 生产环境禁止使用默认JWT密钥！
```

**解决方案**：
```bash
# 设置环境变量
export JWT_SECRET_KEY="your-secure-key"
export SECRET_KEY="your-secure-key"

# 或创建.env文件
echo JWT_SECRET_KEY=your-secure-key >> .env
echo SECRET_KEY=your-secure-key >> .env
```

---

### Q3: 如何清除Redis缓存？

**方法1：重启Redis**（清空所有）
```bash
docker restart xihong_erp_redis
```

**方法2：清除特定缓存**
```bash
docker exec -it xihong_erp_redis redis-cli

# 清除字段辞典缓存
> DEL xihong-erp:field-mapping:*

# 清除数据看板缓存
> DEL xihong-erp:dashboard:*

# 清除所有缓存
> FLUSHDB
```

**方法3：API清除**（待实现）
```python
# 在API中调用
from backend.utils.redis_client import clear_cache
await clear_cache("xihong-erp:field-*", app)
```

---

### Q4: 如何验证Redis是否启用？

**查看启动日志**：
```
✅ 已启用：[OK] Redis缓存已启用: redis://localhost:6379/0
❌ 未启用：[SKIP] Redis缓存未启用: Connection refused
```

**测试缓存效果**：
```bash
# 1. 访问字段辞典（第一次，慢）
curl http://localhost:8001/api/field-mapping/dictionary/fields
# 响应时间：~200ms

# 2. 再次访问（从缓存读取，快）
curl http://localhost:8001/api/field-mapping/dictionary/fields
# 响应时间：~5ms（快40倍！）
```

---

## 📊 启动性能对比

| 启动方式 | PostgreSQL | Redis | 启动时间 | 运行性能 | 推荐场景 |
|---------|-----------|-------|---------|---------|---------|
| **完整启动** | ✅ | ✅ | 0.65秒 | ⭐⭐⭐⭐⭐ 最快 | 生产环境 |
| **快速启动** | ✅ | ❌ | 0.57秒 | ⭐⭐⭐ 正常 | 日常开发 |
| **Docker启动** | ✅ | ✅ | 1.5秒 | ⭐⭐⭐⭐⭐ 最快 | 部署环境 |

---

## 💾 数据持久化

### PostgreSQL数据
- **位置**：Docker Volume（自动持久化）
- **备份**：定期执行 `docker exec xihong_erp_postgres pg_dump ...`

### Redis缓存
- **位置**：内存（重启会清空）
- **特点**：丢失无影响，系统自动重建
- **持久化**：如需要，可配置Redis RDB/AOF

---

## 🎓 最佳实践

### 开发环境

```bash
# 每天启动
start_system_quick.bat  # 快速启动，无Redis

# 需要测试性能时
start_system_with_redis.bat  # 完整启动，有Redis
```

### 生产环境

```bash
# 设置环境变量（一次性）
export ENVIRONMENT=production
export JWT_SECRET_KEY="..."
export SECRET_KEY="..."

# 启动（每次）
start_system_with_redis.bat  # 完整启动

# 或使用Docker Compose
docker-compose -f docker-compose.prod.yml up -d
```

---

## 📝 总结

### 推荐的日常流程

**开发阶段**（快速）：
```bash
1. 启动PostgreSQL（一次）: docker-compose up -d postgres
2. 每天启动ERP: python run.py
3. Redis可选
```

**测试阶段**（完整）：
```bash
1. start_system_with_redis.bat
2. 验证所有功能
3. 测试性能
```

**生产环境**（标准）：
```bash
1. 配置环境变量
2. docker-compose -f docker-compose.prod.yml up -d
3. 监控日志
```

### Redis使用建议

- **开发环境**：可选（不影响功能）
- **测试环境**：推荐（模拟生产性能）
- **生产环境**：必须（95%性能提升）

---

**最后更新**: 2025-11-05  
**维护**: AI Agent Team

