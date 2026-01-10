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

## 📝 GitHub Actions Workflow 规范（v4.20.0）

### 1. SSH 远程命令执行规范

#### ❌ 禁止使用 Heredoc

**问题**：在 GitHub Actions 的 YAML 工作流中使用 heredoc（`<< ENDSSH`）会导致以下问题：

1. **变量展开冲突**：GitHub Actions 的 YAML 解析和 Shell 的 heredoc 解析冲突
2. **变量展开时机不确定**：无法控制哪些变量在哪个阶段展开
3. **引号嵌套复杂**：多层引号嵌套导致解析困难，需要大量转义
4. **错误提示模糊**：语法错误难以定位和修复

**错误示例**：
```yaml
# ❌ 错误：使用 heredoc，变量展开冲突
- name: Deploy
  run: |
    ssh user@host << 'ENDSSH'
    cd ${STAGING_PATH}  # ❌ 不会展开（单引号阻止）
    docker pull image:${IMAGE_TAG}  # ❌ 不会展开
    ENDSSH
```

**错误信息示例**：
```
syntax error: unexpected end of file
wanted 'ENDSSH"'
stat /home/***/docker-compose.yml: no such file or directory
```

#### ✅ 必须使用 `bash -c`

**正确方式**：使用 `bash -c '...'` 执行远程命令，通过引号和转义明确控制变量展开。

**正确示例**：
```yaml
# ✅ 正确：使用 bash -c，变量作用域清晰
- name: Deploy
  run: |
    ssh -o StrictHostKeyChecking=no \
        -o ServerAliveInterval=30 \
        -o ServerAliveCountMax=10 \
        ${PRODUCTION_USER}@${PRODUCTION_HOST} \
      "bash -c '
      set -e
      cd \"${PRODUCTION_PATH}\"  # ✅ GitHub Actions 展开（外层双引号）
      IMAGE_TAG_VAL=\"${IMAGE_TAG}\"  # ✅ GitHub Actions 展开（外层双引号）
      echo \"[INFO] Pulling images with tag: \${IMAGE_TAG_VAL}\"  # ✅ 远程展开（内层单引号，需转义 $）
      docker pull image:\${IMAGE_TAG_VAL}  # ✅ 远程展开（需转义 $）
      '"
```

### 2. 变量展开规则

#### 变量展开顺序

```
1. GitHub Actions 解析 YAML
   ↓
   ${PRODUCTION_PATH} → "/opt/xihong_erp"  （外层双引号展开）
   ${IMAGE_TAG} → "v4.20.0"  （外层双引号展开）

2. SSH 传递展开后的命令到远程服务器
   ↓
   ssh user@host "bash -c 'cd \"/opt/xihong_erp\" ...'"

3. 远程服务器执行 bash -c
   ↓
   在远程服务器上：
   - cd "/opt/xihong_erp"  （直接执行）
   - IMAGE_TAG_VAL="v4.20.0"  （赋值）
   - echo "[INFO] Pulling images with tag: ${IMAGE_TAG_VAL}"  （内层单引号中的 \${IMAGE_TAG_VAL} 展开为 $IMAGE_TAG_VAL）

4. 远程服务器展开变量
   ↓
   ${IMAGE_TAG_VAL} → "v4.20.0"  （在远程展开）
```

#### 转义规则

| 变量类型 | 示例 | 转义方式 | 展开时机 |
|---------|------|---------|---------|
| **GitHub Actions 变量** | `${PRODUCTION_PATH}` | 不转义 | 本地（GitHub Actions 运行时） |
| **GitHub Actions 表达式** | `${{ secrets.GITHUB_TOKEN }}` | 不转义 | 本地（GitHub Actions 运行时） |
| **远程 Shell 变量** | `\$retry` | 转义 `$` | 远程（SSH 服务器上） |
| **远程引号** | `\"text\"` | 转义 `"` | 远程（SSH 服务器上） |
| **命令替换** | `\$(date ...)` | 转义 `$` | 远程（SSH 服务器上） |

### 3. 最佳实践

#### ✅ 推荐做法

1. **使用 `bash -c` 替代 heredoc**：
   ```yaml
   ssh user@host "bash -c '...'"
   ```

2. **明确变量作用域**：
   - 外层双引号：GitHub Actions 变量（不转义）
   - 内层单引号：远程变量（需转义 `$`、`"`）

3. **添加错误处理**：
   ```yaml
   "bash -c '
   set -e  # 遇到错误立即退出
   cd \"${PRODUCTION_PATH}\"
   # ... 命令 ...
   '"
   ```

4. **添加连接保活**：
   ```yaml
   ssh -o ServerAliveInterval=30 \
       -o ServerAliveCountMax=10 \
       user@host "bash -c '...'"
   ```

#### ❌ 避免做法

1. **禁止使用 heredoc**：
   ```yaml
   # ❌ 禁止
   ssh user@host << 'ENDSSH'
   ...
   ENDSSH
   ```

2. **避免引号混淆**：
   ```yaml
   # ❌ 禁止：引号嵌套混乱
   ssh user@host "bash -c \"cd ${PATH}\""
   
   # ✅ 正确：引号嵌套清晰
   ssh user@host "bash -c 'cd \"${PATH}\"'"
   ```

3. **避免变量转义错误**：
   ```yaml
   # ❌ 错误：远程变量未转义
   ssh user@host "bash -c 'echo ${VAR}'"  # ${VAR} 在本地展开（错误）
   
   # ✅ 正确：远程变量已转义
   ssh user@host "bash -c 'echo \${VAR}'"  # ${VAR} 在远程展开（正确）
   ```

### 4. 常见错误和解决方案

#### 错误1：变量未展开

**症状**：`stat /home/***/docker-compose.yml: no such file or directory`

**原因**：使用 `<< 'ENDSSH'`（单引号），阻止了所有变量展开

**解决**：改用 `bash -c '...'`，明确控制变量展开

#### 错误2：语法错误

**症状**：`syntax error: unexpected end of file` 或 `wanted 'ENDSSH"'`

**原因**：Heredoc 分隔符引用方式导致 YAML 解析器混淆

**解决**：改用 `bash -c '...'`，避免 heredoc 语法问题

#### 错误3：变量展开时机错误

**症状**：变量值错误或为空

**原因**：变量在不同阶段展开，导致值不正确

**解决**：使用 `bash -c`，通过转义明确控制变量展开时机

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

**最后更新**: 2026-01-10  
**维护**: AI Agent Team  
**状态**: ✅ 企业级标准（已更新 GitHub Actions Workflow 语法规范、Celery Worker、Nginx、Redis 监控和故障排查）

