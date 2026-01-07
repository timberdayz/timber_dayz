# 部署和运维规范 - 企业级ERP标准

**版本**: v4.4.0  
**更新**: 2025-01-30  
**标准**: 企业级部署和运维标准

---

## 🚀 CI/CD流程

### 1. 持续集成（CI）
- ✅ **自动化测试**: PR时自动运行单元测试、集成测试
- ✅ **代码检查**: 自动运行Ruff、Pylint、mypy、bandit
- ✅ **覆盖率检查**: 检查测试覆盖率是否达标
- ✅ **自动化构建**: 自动构建Docker镜像

### 2. 持续部署（CD）
- ✅ **Staging环境**: 自动部署到Staging环境
- ✅ **生产环境**: 经过审批后部署到生产环境
- ✅ **回滚机制**: 支持一键回滚到上一版本

---

## 📦 部署策略

### 1. 蓝绿部署（零停机）
- ✅ **双环境**: 同时运行两个版本
- ✅ **流量切换**: 逐步切换流量到新版本
- ✅ **快速回滚**: 出问题时快速切回旧版本

### 2. 金丝雀发布（渐进式）
- ✅ **小流量**: 先部署到小部分流量
- ✅ **监控**: 监控新版本的健康状况
- ✅ **逐步扩大**: 逐步扩大流量比例

### 3. 回滚策略
- ✅ **一键回滚**: 支持一键回滚到上一版本
- ✅ **版本管理**: 保留最近5个版本
- ✅ **数据兼容**: 确保数据兼容性

---

## 🏥 运维标准

### 1. 健康检查
- ✅ **就绪检查**: `/health/ready` - 服务是否就绪
- ✅ **存活检查**: `/health/live` - 服务是否存活
- ✅ **健康检查**: `/health` - 综合健康状态

### 2. 优雅关闭
- ✅ **SIGTERM处理**: 优雅处理SIGTERM信号
- ✅ **请求完成**: 等待正在处理的请求完成
- ✅ **资源清理**: 清理数据库连接、文件句柄等资源

### 3. 配置管理
- ✅ **环境变量**: 使用环境变量管理配置
- ✅ **配置验证**: 启动时验证配置完整性
- ✅ **配置热更新**: 支持配置热更新（不重启服务）

---

## 📊 监控和告警

### 1. 系统监控
- ✅ **资源监控**: CPU、内存、磁盘、网络
- ✅ **应用监控**: 请求数、响应时间、错误率
- ✅ **业务监控**: GMV、订单量、转化率

### 2. 告警规则
- ✅ **错误率告警**: 错误率 > 5%
- ✅ **响应时间告警**: P95 > 2s
- ✅ **资源告警**: CPU/内存 > 80%

### 3. Celery Worker 监控
- ✅ **任务执行时间**: 监控任务执行时间（告警阈值：>30分钟）
- ✅ **任务失败率**: 监控任务失败率（告警阈值：>10%）
- ✅ **任务队列长度**: 监控任务队列长度（告警阈值：>100）
- ✅ **Worker 状态**: 监控 Worker 是否正常运行

**监控命令**:
```bash
# 查看活跃任务
docker-compose -f docker-compose.prod.yml exec celery-worker celery -A backend.celery_app inspect active

# 查看任务统计
docker-compose -f docker-compose.prod.yml exec celery-worker celery -A backend.celery_app inspect stats

# 查看任务队列
docker-compose -f docker-compose.prod.yml exec celery-worker celery -A backend.celery_app inspect scheduled
```

### 4. Nginx 监控
- ✅ **请求数**: 监控 Nginx 处理的请求数
- ✅ **响应时间**: 监控 Nginx 响应时间
- ✅ **限流触发**: 监控限流触发次数（429 状态码）
- ✅ **错误率**: 监控 5xx 错误率（告警阈值：>1%）

**监控命令**:
```bash
# 查看 Nginx 访问日志
docker-compose -f docker-compose.prod.yml logs -f nginx | grep -E "GET|POST|PUT|DELETE"

# 查看 Nginx 错误日志
docker-compose -f docker-compose.prod.yml logs -f nginx | grep -E "error|warn"

# 查看限流触发情况
docker-compose -f docker-compose.prod.yml logs nginx | grep "429"
```

### 5. Redis 监控
- ✅ **内存使用率**: 监控 Redis 内存使用率（告警阈值：>80%）
- ✅ **连接数**: 监控 Redis 连接数（告警阈值：>1000）
- ✅ **命令执行时间**: 监控命令执行时间（告警阈值：>100ms）
- ✅ **持久化状态**: 监控 AOF 和 RDB 持久化状态

**监控命令**:
```bash
# 查看 Redis 信息
docker-compose -f docker-compose.prod.yml exec redis redis-cli INFO

# 查看 Redis 内存使用
docker-compose -f docker-compose.prod.yml exec redis redis-cli INFO memory

# 查看 Redis 连接数
docker-compose -f docker-compose.prod.yml exec redis redis-cli INFO clients
```

---

## 🔧 故障排查

### 1. Celery Worker 故障排查

**问题：任务执行失败**

```bash
# 查看任务错误日志
docker-compose -f docker-compose.prod.yml logs celery-worker | grep -i error

# 查看任务详情
docker-compose -f docker-compose.prod.yml exec celery-worker celery -A backend.celery_app inspect active

# 查看任务结果
docker-compose -f docker-compose.prod.yml exec celery-worker celery -A backend.celery_app result <task_id>
```

**问题：任务队列堆积**

```bash
# 查看队列长度
docker-compose -f docker-compose.prod.yml exec celery-worker celery -A backend.celery_app inspect scheduled

# 增加 Worker 并发数
# 修改 docker-compose.prod.yml 中的 celery-worker 服务，添加环境变量：
# CELERY_WORKER_CONCURRENCY: 8
```

**问题：Worker 无法连接 Redis**

```bash
# 检查 Redis 连接
docker-compose -f docker-compose.prod.yml exec redis redis-cli ping

# 检查 Redis 密码配置
docker-compose -f docker-compose.prod.yml exec celery-worker env | grep REDIS
```

### 2. Nginx 故障排查

**问题：502 Bad Gateway**

```bash
# 检查后端服务是否正常运行
docker-compose -f docker-compose.prod.yml ps backend

# 检查后端服务日志
docker-compose -f docker-compose.prod.yml logs backend | tail -50

# 检查 Nginx 配置
docker-compose -f docker-compose.prod.yml exec nginx nginx -t
```

**问题：限流过于严格**

```bash
# 查看限流配置
cat nginx/nginx.prod.conf | grep -A 5 "limit_req"

# 调整限流规则（修改 nginx/nginx.prod.conf）
# 重新加载配置
docker-compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

**问题：SSL 证书过期**

```bash
# 检查证书有效期
openssl x509 -in nginx/ssl/cert.pem -noout -dates

# 更新证书（Let's Encrypt）
sudo certbot renew
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem nginx/ssl/cert.pem
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem nginx/ssl/key.pem
docker-compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

### 3. Redis 故障排查

**问题：Redis 内存不足**

```bash
# 查看内存使用情况
docker-compose -f docker-compose.prod.yml exec redis redis-cli INFO memory

# 清理过期键
docker-compose -f docker-compose.prod.yml exec redis redis-cli FLUSHDB

# 增加 Redis 内存限制（修改 docker-compose.prod.yml）
# redis:
#   deploy:
#     resources:
#       limits:
#         memory: 2G
```

**问题：Redis 连接失败**

```bash
# 检查 Redis 服务状态
docker-compose -f docker-compose.prod.yml ps redis

# 检查 Redis 日志
docker-compose -f docker-compose.prod.yml logs redis | tail -50

# 测试 Redis 连接
docker-compose -f docker-compose.prod.yml exec redis redis-cli -a <password> ping
```

**问题：任务丢失**

```bash
# 检查 Redis 持久化状态
docker-compose -f docker-compose.prod.yml exec redis redis-cli INFO persistence

# 检查 AOF 文件
docker-compose -f docker-compose.prod.yml exec redis ls -lh /data/appendonly.aof

# 检查 RDB 文件
docker-compose -f docker-compose.prod.yml exec redis ls -lh /data/dump.rdb
```

---

## ⚡ 性能优化

### 1. Celery Worker 性能优化

**增加并发数**:
```yaml
# docker-compose.prod.yml
celery-worker:
  environment:
    CELERY_WORKER_CONCURRENCY: 8  # 根据 CPU 核心数调整
```

**优化任务优先级**:
- 高优先级任务（priority=10）：立即执行
- 中优先级任务（priority=5）：正常执行
- 低优先级任务（priority=1）：最后执行

**任务批处理**:
- 对于大量小任务，使用批量处理减少开销
- 使用 `chord` 和 `group` 进行任务分组

### 2. Nginx 性能优化

**启用缓存**:
```nginx
# nginx/nginx.prod.conf
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m max_size=1g;
proxy_cache api_cache;
proxy_cache_valid 200 5m;
```

**启用压缩**:
```nginx
gzip on;
gzip_types text/plain text/css application/json application/javascript;
gzip_min_length 1000;
```

**连接池优化**:
```nginx
upstream backend {
    server backend:8000 max_fails=3 fail_timeout=30s;
    keepalive 32;  # 保持连接池
}
```

### 3. Redis 性能优化

**内存优化**:
```bash
# 设置最大内存
docker-compose -f docker-compose.prod.yml exec redis redis-cli CONFIG SET maxmemory 2gb

# 设置淘汰策略
docker-compose -f docker-compose.prod.yml exec redis redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

**持久化优化**:
```bash
# 调整 AOF 同步频率（性能 vs 数据安全）
# appendfsync everysec  # 每秒同步（推荐）
# appendfsync always    # 每次写入同步（最安全，但性能较低）
# appendfsync no        # 不主动同步（最快，但可能丢失数据）
```

**连接池优化**:
- 使用连接池减少连接开销
- 设置合理的连接超时时间
- 监控连接数，避免连接泄漏

---

**最后更新**: 2026-01-03  
**维护**: AI Agent Team  
**状态**: ✅ 企业级标准（已更新 Celery Worker、Nginx、Redis 监控和故障排查）

