# 🚀 西虹 ERP 系统 - 生产环境部署指南

**版本**: v4.0.0  
**日期**: 2025-10-23  
**适用环境**: 生产环境

---

## 📋 部署前准备

### 1. 系统要求

**硬件要求**:

- CPU: 4 核心或以上
- 内存: 8GB 或以上
- 磁盘: 100GB 或以上（SSD 推荐）
- 网络: 100Mbps 或以上

**软件要求**:

- 操作系统: Ubuntu 20.04 LTS / CentOS 8+ / Debian 11+
- Docker: 20.10+
- Docker Compose: 2.0+
- Git: 2.30+

### 2. 域名和 SSL 证书

**域名配置**:

- 主域名: `your-domain.com`
- API 子域名: `api.your-domain.com`（可选）

**SSL 证书**:

- 推荐使用 Let's Encrypt 免费 SSL 证书
- 或购买商业 SSL 证书
- 证书文件放置在 `nginx/ssl/` 目录

### 3. 安全配置

**防火墙规则**:

```bash
# 开放HTTP和HTTPS端口
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# 开放SSH端口（如需远程管理）
sudo ufw allow 22/tcp

# 启用防火墙
sudo ufw enable
```

**SSH 密钥配置**:

```bash
# 生成SSH密钥
ssh-keygen -t rsa -b 4096 -C "your_email@example.com"

# 复制公钥到服务器
ssh-copy-id user@your-server-ip
```

---

## 🔧 部署步骤

### Step 1: 克隆代码库

```bash
# 克隆代码
git clone https://github.com/your-org/xihong-erp.git
cd xihong-erp

# 切换到生产分支
git checkout main
```

### Step 2: 配置环境变量

```bash
# 复制配置模板
cp .env.production.example .env.production

# 编辑配置文件
nano .env.production
```

**必须修改的配置**:

- `POSTGRES_PASSWORD` - 数据库密码
- `REDIS_PASSWORD` - Redis 密码
- `SECRET_KEY` - 应用密钥
- `JWT_SECRET_KEY` - JWT 密钥
- `ALLOWED_HOSTS` - 允许的域名
- `VITE_API_BASE_URL` - API 地址

### Step 3: 配置 SSL 证书

**使用 Let's Encrypt**:

```bash
# 安装certbot
sudo apt-get install certbot

# 获取SSL证书
sudo certbot certonly --standalone -d your-domain.com -d www.your-domain.com

# 复制证书到项目目录
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem nginx/ssl/cert.pem
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem nginx/ssl/key.pem
```

**使用商业证书**:

```bash
# 将证书文件复制到项目目录
cp your-cert.pem nginx/ssl/cert.pem
cp your-key.pem nginx/ssl/key.pem
```

### Step 4: 启用 HTTPS 配置

编辑 `nginx/nginx.prod.conf`，取消 HTTPS 配置的注释：

```nginx
# 取消以下部分的注释
server {
    listen 443 ssl http2;
    server_name your-domain.com;
    # ... SSL配置 ...
}
```

### Step 5: 构建和启动服务

```bash
# 构建镜像
docker-compose -f docker-compose.prod.yml build

# 启动服务
docker-compose -f docker-compose.prod.yml up -d

# 查看服务状态
docker-compose -f docker-compose.prod.yml ps
```

### Step 6: 初始化数据库

```bash
# 进入后端容器
docker-compose -f docker-compose.prod.yml exec backend bash

# 运行数据库迁移
alembic upgrade head

# 创建管理员用户（可选）
python -c "from backend.services.auth_service import auth_service; print(auth_service.hash_password('your_admin_password'))"

# 退出容器
exit
```

### Step 7: 启动 Celery Worker（异步任务处理）

**使用 Docker Compose（推荐）**：

```bash
# docker-compose.prod.yml 已包含 celery-worker 服务配置
# 启动 Celery Worker
docker-compose -f docker-compose.prod.yml up -d celery-worker

# 启动 Celery Beat（定时任务，可选）
docker-compose -f docker-compose.prod.yml up -d celery-beat

# 查看 Celery Worker 状态
docker-compose -f docker-compose.prod.yml logs -f celery-worker
```

**验证 Celery Worker**：

```bash
# 检查 Celery Worker 是否正常运行
docker-compose -f docker-compose.prod.yml exec celery-worker celery -A backend.celery_app inspect active

# 查看任务队列
docker-compose -f docker-compose.prod.yml exec celery-worker celery -A backend.celery_app inspect scheduled
```

**配置说明**：

- Celery Worker 使用 `restart: always` 实现自动重启
- 任务持久化存储在 Redis 中，服务器重启后自动恢复
- 任务队列：`data_sync`（数据同步）、`scheduled`（定时任务）
- 并发数：默认 4（可通过环境变量 `CELERY_WORKER_CONCURRENCY` 调整）

### Step 8: 配置 Nginx 反向代理

**Nginx 配置已包含在 `docker-compose.prod.yml` 中**：

```bash
# Nginx 服务已自动启动
# 查看 Nginx 配置
docker-compose -f docker-compose.prod.yml exec nginx nginx -t

# 重新加载 Nginx 配置（修改配置后）
docker-compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

**Nginx 功能**：

- 反向代理：将请求转发到后端服务（`backend:8000`）
- 静态文件服务：提供前端静态文件
- 限流保护：按 IP 和 API 路径限流
- SSL 终止：处理 HTTPS 请求

**限流配置**（`nginx/nginx.prod.conf`）：

- 通用 API：200 次/分钟（burst=50）
- 数据同步 API：30 次/分钟（burst=10）
- 认证 API：10 次/分钟（burst=3）
- 连接数限制：每个 IP 最多 20 个并发连接

### Step 9: 配置 Redis 缓存和任务队列

**Redis 配置已包含在 `docker-compose.prod.yml` 中**：

```bash
# Redis 服务已自动启动
# 查看 Redis 状态
docker-compose -f docker-compose.prod.yml exec redis redis-cli ping

# 查看 Redis 信息
docker-compose -f docker-compose.prod.yml exec redis redis-cli INFO
```

**Redis 功能**：

- **任务队列**：Celery 使用 Redis 作为消息代理和结果后端
- **缓存服务**：存储频繁访问的数据（账号列表、组件版本等）
- **持久化**：配置了 AOF 和 RDB 持久化，确保任务不丢失

**Redis 持久化配置**：

- AOF（Append Only File）：实时记录所有写操作
- RDB（Redis Database）：定期快照备份
- 数据存储在 Docker 卷 `redis_data_prod` 中

### Step 10: 验证部署

```bash
# 检查服务健康状态
curl http://localhost/health

# 检查HTTPS访问
curl https://your-domain.com/health

# 检查 Celery Worker 状态
docker-compose -f docker-compose.prod.yml exec celery-worker celery -A backend.celery_app inspect active

# 检查 Redis 连接
docker-compose -f docker-compose.prod.yml exec redis redis-cli ping

# 查看所有服务日志
docker-compose -f docker-compose.prod.yml logs -f
```

---

## 📦 备份配置

### 自动备份设置

**配置定时备份**:

```bash
# 编辑crontab
crontab -e

# 添加备份任务（每天凌晨2点执行）
0 2 * * * /path/to/xihong-erp/scripts/backup_database.sh >> /var/log/backup.log 2>&1
```

**手动备份**:

```bash
# 执行备份脚本
./scripts/backup_database.sh

# 查看备份文件
ls -lh backups/
```

### 备份恢复

**恢复数据库**:

```bash
# 列出可用备份
ls -lh backups/

# 恢复指定备份
./scripts/restore_database.sh backups/xihong_erp_20251023_020000.sql.gz
```

---

## 📊 监控配置

### Prometheus 监控

**启动 Prometheus**:

```bash
# 修改docker-compose.prod.yml，添加Prometheus服务
# 启动监控服务
docker-compose -f docker-compose.prod.yml up -d prometheus grafana
```

**访问监控面板**:

- Prometheus: `http://your-domain.com:9090`
- Grafana: `http://your-domain.com:3001`

### 日志监控

**查看应用日志**:

```bash
# 后端日志
docker-compose -f docker-compose.prod.yml logs -f backend

# 前端日志
docker-compose -f docker-compose.prod.yml logs -f frontend

# Nginx日志
docker-compose -f docker-compose.prod.yml logs -f nginx

# 所有服务日志
docker-compose -f docker-compose.prod.yml logs -f
```

**日志文件位置**:

- 后端日志: `logs/backend/`
- Nginx 日志: `logs/nginx/`
- 数据库日志: Docker 容器内部

---

## 🔐 安全加固

### 1. 数据库安全

**限制数据库访问**:

```yaml
# 修改docker-compose.prod.yml
postgres:
  ports:
    - "127.0.0.1:5432:5432" # 只允许本地访问
```

**定期更新密码**:

```bash
# 更改数据库密码
docker-compose -f docker-compose.prod.yml exec postgres psql -U erp_user -c "ALTER USER erp_user WITH PASSWORD 'new_password';"
```

### 2. API 安全

**启用请求限流**:

```python
# 在backend/main.py中配置
from slowapi import Limiter
limiter = Limiter(key_func=get_remote_address)
```

**配置 CORS**:

```python
# 只允许特定域名访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-domain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 3. 系统安全

**定期更新系统**:

```bash
# 更新系统包
sudo apt-get update && sudo apt-get upgrade -y

# 更新Docker镜像
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml up -d
```

**安全审计**:

```bash
# 检查Docker容器安全
docker scan xihong_erp_backend_prod

# 检查端口开放情况
sudo netstat -tulpn
```

---

## 🚀 性能优化

### 1. 数据库优化

**配置数据库参数**:

```sql
-- 调整PostgreSQL配置
ALTER SYSTEM SET shared_buffers = '2GB';
ALTER SYSTEM SET effective_cache_size = '6GB';
ALTER SYSTEM SET maintenance_work_mem = '512MB';
ALTER SYSTEM SET work_mem = '64MB';

-- 重启PostgreSQL
SELECT pg_reload_conf();
```

**创建索引**:

```sql
-- 为常用查询创建索引
CREATE INDEX CONCURRENTLY idx_orders_date ON fact_sales_orders(order_date);
CREATE INDEX CONCURRENTLY idx_products_sku ON dim_products(sku);
```

### 2. 应用优化

**增加 Worker 数量**:

```yaml
# 修改docker-compose.prod.yml
backend:
  environment:
    GUNICORN_WORKERS: 8 # 根据CPU核心数调整
```

**配置缓存**:

```python
# 启用Redis缓存
REDIS_CACHE_ENABLED=true
REDIS_CACHE_TTL=3600
```

### 3. 前端优化

**启用 CDN**:

- 将静态资源上传到 CDN
- 配置 DNS 解析到 CDN

**配置缓存策略**:

```nginx
# 在nginx配置中添加
location ~* \.(jpg|jpeg|png|gif|ico|css|js)$ {
    expires 365d;
    add_header Cache-Control "public, immutable";
}
```

---

## 🔄 更新和维护

### 代码更新

**无停机更新**:

```bash
# 拉取最新代码
git pull origin main

# 构建新镜像
docker-compose -f docker-compose.prod.yml build

# 滚动更新服务
docker-compose -f docker-compose.prod.yml up -d --no-deps --build backend
docker-compose -f docker-compose.prod.yml up -d --no-deps --build frontend
```

### 数据库迁移

**执行数据库迁移**:

```bash
# 备份数据库
./scripts/backup_database.sh

# 执行迁移
docker-compose -f docker-compose.prod.yml exec backend alembic upgrade head

# 验证迁移
docker-compose -f docker-compose.prod.yml exec backend alembic current
```

### 回滚操作

**回滚代码**:

```bash
# 回滚到上一个版本
git checkout <previous-commit-hash>
docker-compose -f docker-compose.prod.yml up -d --build
```

**回滚数据库**:

```bash
# 恢复备份
./scripts/restore_database.sh backups/xihong_erp_<timestamp>.sql.gz

# 或使用Alembic回滚
docker-compose -f docker-compose.prod.yml exec backend alembic downgrade -1
```

---

## 📊 监控和告警配置

### 概述

系统使用 Prometheus + AlertManager + Grafana 实现监控和告警：

| 组件 | 端口 | 用途 |
|------|------|------|
| Celery Exporter | 9808 | 导出 Celery 任务指标 |
| Prometheus | 9090 | 指标收集和存储 |
| AlertManager | 9093 | 告警管理和通知 |
| Grafana | 3001 | 可视化仪表板 |

### Step 1: 配置环境变量

在 `.env.production` 中添加以下配置：

```bash
# Redis 密码（Celery Exporter 需要）
REDIS_PASSWORD=your_redis_password

# AlertManager SMTP 配置
SMTP_HOST=smtp.example.com:587
SMTP_FROM=alerts@your-domain.com
SMTP_USERNAME=alerts@your-domain.com
SMTP_PASSWORD=your_smtp_password

# 告警邮件收件人
ALERT_EMAIL_TO=ops-team@your-domain.com
ALERT_EMAIL_CRITICAL=critical-alerts@your-domain.com
ALERT_EMAIL_WARNING=warning-alerts@your-domain.com
ALERT_EMAIL_CELERY=celery-alerts@your-domain.com

# Grafana 管理员密码
GRAFANA_ADMIN_PASSWORD=your_grafana_password
```

### Step 2: 启动监控服务

```bash
# 方式一：使用独立的监控 Docker Compose 文件
docker-compose -f docker/docker-compose.monitoring.yml up -d

# 方式二：Celery Exporter 已在 docker-compose.prod.yml 中配置
# 只需启动主服务即可包含 Celery Exporter
docker-compose -f docker-compose.prod.yml up -d
```

### Step 3: 验证监控服务

```bash
# 运行测试脚本
python scripts/test_monitoring_setup.py

# 或手动检查各服务
curl http://localhost:9808/metrics   # Celery Exporter
curl http://localhost:9090/-/healthy # Prometheus
curl http://localhost:9093/-/healthy # AlertManager
curl http://localhost:3001/api/health # Grafana
```

### Step 4: 配置告警通知

1. **邮件通知**：已在 `monitoring/alertmanager.yml` 中配置
2. **Webhook 通知**（可选）：取消注释 `alertmanager.yml` 中的 webhook_configs
3. **企业微信/钉钉**：添加对应的 receiver 配置

### 访问监控界面

- **Prometheus**: http://your-domain.com:9090
- **AlertManager**: http://your-domain.com:9093
- **Grafana**: http://your-domain.com:3001 (默认用户: admin)

### 告警规则说明

| 告警名称 | 严重级别 | 触发条件 |
|---------|---------|---------|
| HighCeleryTaskFailureRate | Warning | 任务失败率 > 10%，持续 5 分钟 |
| HighCeleryQueueLength | Warning | 队列长度 > 100，持续 5 分钟 |
| HighCeleryTaskExecutionTime | Warning | P95 执行时间 > 30 分钟，持续 10 分钟 |
| CeleryWorkerDown | Critical | Worker 离线，持续 2 分钟 |
| CeleryRedisConnectionFailed | Critical | Redis 连接失败 |

> **注意**: 告警阈值是初始值，建议根据实际业务情况调整。

---

## 🆘 故障排除

### 常见问题

**1. 服务无法启动**:

```bash
# 检查日志
docker-compose -f docker-compose.prod.yml logs

# 检查端口占用
sudo netstat -tulpn | grep :8000

# 重启服务
docker-compose -f docker-compose.prod.yml restart
```

**2. 数据库连接失败**:

```bash
# 检查数据库状态
docker-compose -f docker-compose.prod.yml exec postgres pg_isready

# 检查数据库日志
docker-compose -f docker-compose.prod.yml logs postgres

# 重启数据库
docker-compose -f docker-compose.prod.yml restart postgres
```

**3. 内存不足**:

```bash
# 检查内存使用
docker stats

# 调整服务资源限制
# 编辑docker-compose.prod.yml中的resources配置
```

### 应急处理

**系统过载**:

```bash
# 临时限制请求
sudo iptables -A INPUT -p tcp --dport 80 -m limit --limit 25/minute --limit-burst 100 -j ACCEPT

# 增加Worker数量
docker-compose -f docker-compose.prod.yml scale backend=4
```

**数据丢失**:

```bash
# 立即停止服务
docker-compose -f docker-compose.prod.yml stop

# 恢复最近的备份
./scripts/restore_database.sh backups/xihong_erp_latest.sql.gz

# 重启服务
docker-compose -f docker-compose.prod.yml start
```

---

## 📞 联系支持

**技术支持**:

- 邮箱: support@your-company.com
- 电话: +86-xxx-xxxx-xxxx
- 文档: https://docs.your-domain.com

**问题反馈**:

- GitHub Issues: https://github.com/your-org/xihong-erp/issues
- 企业微信群: [加入方式]

---

**部署完成后，请确保**:

- ✅ 所有服务运行正常
- ✅ HTTPS 访问正常
- ✅ 数据库备份正常
- ✅ 监控告警配置完成
- ✅ 安全加固措施实施
- ✅ 性能指标达标

**祝您部署顺利！** 🚀
