# 部署指南

**版本**: v4.x (Phase 3 DSS架构)  
**更新时间**: 2025-11-22

---

## 📋 系统要求

### 硬件要求

| 环境 | CPU | 内存 | 存储 |
|------|-----|------|------|
| 开发环境 | 2核+ | 4GB+ | 20GB+ |
| 生产环境 | 4核+ | 8GB+ | 100GB+ |

### 软件要求

- **操作系统**: Windows 10+, Linux (Ubuntu 20.04+), macOS 11+
- **Docker**: 20.10+
- **Docker Compose**: 1.29+
- **Python**: 3.9+
- **Node.js**: 16+
- **PostgreSQL**: 15+ (Docker容器)

---

## 🚀 快速开始（开发环境）

### 1. 克隆仓库

```bash
git clone <repository_url>
cd xihong_erp
```

### 2. 配置环境变量

```bash
# 复制配置文件
cp config/production.example.env .env

# 编辑.env文件，填写实际配置
# 至少修改以下项：
# - POSTGRES_PASSWORD
# - SUPERSET_GUEST_TOKEN_SECRET
# - API_SECRET_KEY
# - JWT_SECRET_KEY
```

### 3. 启动Docker服务

```bash
# 启动PostgreSQL、Redis、pgAdmin
docker-compose up -d

# 检查服务状态
docker ps
```

### 4. 初始化数据库

```bash
# 进入项目目录
cd backend

# 运行数据库迁移（如果有）
# python scripts/migrate_database.py

# 或直接运行SQL脚本
# docker exec -i xihong_erp_postgres psql -U erp_user -d xihong_erp < sql/deploy_views.sql
```

### 5. 启动后端服务

```bash
# 方式1：使用统一启动脚本
python run.py

# 方式2：单独启动后端
cd backend
python main.py
```

后端服务将在 `http://localhost:8001` 启动

### 6. 启动前端服务

```bash
# 进入前端目录
cd frontend

# 安装依赖（首次）
npm install

# 启动开发服务器
npm run dev
```

前端服务将在 `http://localhost:5173` 启动

### 7. 访问系统

- **前端界面**: http://localhost:5173
- **后端API**: http://localhost:8001
- **API文档**: http://localhost:8001/docs
- **pgAdmin**: http://localhost:5051

---

## 🐳 Docker部署（推荐）

### 完整Docker Compose配置

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    container_name: xihong_erp_postgres
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:latest
    container_name: xihong_erp_redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  backend:
    build: ./backend
    container_name: xihong_erp_backend
    environment:
      DATABASE_URL: ${DATABASE_URL}
      REDIS_HOST: redis
      SUPERSET_URL: http://superset:8088
    ports:
      - "8001:8001"
    depends_on:
      - postgres
      - redis
    volumes:
      - ./backend:/app
      - ./data:/data

  frontend:
    build: ./frontend
    container_name: xihong_erp_frontend
    environment:
      VITE_API_URL: http://localhost:8001
    ports:
      - "5173:5173"
    depends_on:
      - backend
    volumes:
      - ./frontend:/app

volumes:
  postgres_data:
  redis_data:
```

### 启动所有服务

```bash
docker-compose up -d
```

---

## 🔧 Superset部署（可选）

### 1. 使用提供的Docker Compose配置

```bash
# 使用Phase 2创建的配置
docker-compose -f docker-compose.superset.yml up -d
```

### 2. 初始化Superset

**Linux/Mac**:
```bash
bash scripts/deploy_superset.sh
```

**Windows**:
```powershell
.\scripts\deploy_superset.ps1
```

### 3. 访问Superset

- URL: http://localhost:8088
- 默认账号: admin / admin

**⚠️ 重要**: 生产环境必须修改默认密码！

---

## 📊 数据库迁移

### A类数据表创建

```bash
# 连接到PostgreSQL容器
docker exec -it xihong_erp_postgres psql -U erp_user -d xihong_erp

# 创建销售目标表
CREATE TABLE IF NOT EXISTS sales_targets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shop_id VARCHAR(100) NOT NULL,
    year_month VARCHAR(7) NOT NULL,
    target_sales_amount DECIMAL(15,2) NOT NULL,
    target_order_count INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(100),
    CONSTRAINT uq_sales_targets_shop_month UNIQUE (shop_id, year_month)
);

# 创建战役目标表
CREATE TABLE IF NOT EXISTS campaign_targets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform_code VARCHAR(50) NOT NULL,
    campaign_name VARCHAR(255) NOT NULL,
    campaign_type VARCHAR(100),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    target_gmv DECIMAL(15,2) NOT NULL,
    target_roi DECIMAL(10,2),
    budget_amount DECIMAL(15,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(100)
);

# 创建经营成本表（会自动创建，也可手动创建）
CREATE TABLE IF NOT EXISTS operating_costs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shop_id VARCHAR(100) NOT NULL,
    year_month VARCHAR(7) NOT NULL,
    rent DECIMAL(15,2) DEFAULT 0,
    salary DECIMAL(15,2) DEFAULT 0,
    marketing DECIMAL(15,2) DEFAULT 0,
    logistics DECIMAL(15,2) DEFAULT 0,
    utilities DECIMAL(15,2) DEFAULT 0,
    other DECIMAL(15,2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(100),
    CONSTRAINT uq_operating_costs_shop_month UNIQUE (shop_id, year_month)
);
```

---

## 🔒 安全配置

### 1. 修改所有默认密码

```bash
# PostgreSQL密码
POSTGRES_PASSWORD=strong_password_here

# Superset密码
SUPERSET_PASSWORD=strong_password_here

# API密钥
API_SECRET_KEY=long_random_string_here
JWT_SECRET_KEY=another_long_random_string
SUPERSET_GUEST_TOKEN_SECRET=yet_another_secret
```

### 2. 配置HTTPS（生产环境必须）

使用Nginx反向代理：

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:5173;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api {
        proxy_pass http://localhost:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 3. 配置防火墙

```bash
# 只开放必要端口
ufw allow 80/tcp
ufw allow 443/tcp
ufw deny 5432/tcp  # PostgreSQL不对外开放
ufw deny 6379/tcp  # Redis不对外开放
```

---

## 📈 监控和日志

### 1. 查看日志

```bash
# Docker容器日志
docker logs xihong_erp_backend -f
docker logs xihong_erp_frontend -f
docker logs xihong_erp_postgres -f

# 应用日志
tail -f logs/xihong_erp.log
```

### 2. 监控指标

- **CPU使用率**: `docker stats`
- **内存使用**: `docker stats`
- **磁盘空间**: `df -h`
- **数据库连接数**: 
  ```sql
  SELECT count(*) FROM pg_stat_activity WHERE datname = 'xihong_erp';
  ```

---

## 🔄 备份策略

### 数据库备份

```bash
# 自动备份脚本
docker exec xihong_erp_postgres pg_dump -U erp_user xihong_erp > backups/xihong_erp_$(date +%Y%m%d_%H%M%S).sql

# 恢复
docker exec -i xihong_erp_postgres psql -U erp_user -d xihong_erp < backups/xihong_erp_20251122_120000.sql
```

### 定时备份（Linux）

```bash
# 添加cron任务
crontab -e

# 每天凌晨2点备份
0 2 * * * /path/to/backup_script.sh
```

---

## 🐛 故障排查

### 后端无法启动

1. 检查PostgreSQL是否运行：`docker ps | grep postgres`
2. 检查环境变量配置：`cat .env`
3. 查看错误日志：`docker logs xihong_erp_backend`

### 前端无法访问API

1. 检查CORS配置：`CORS_ORIGINS`
2. 检查API URL：`VITE_API_URL`
3. 检查网络连接：`curl http://localhost:8001/health`

### Superset无法加载

1. 检查Superset服务：`curl http://localhost:8088/health`
2. 检查Guest Token配置：`SUPERSET_GUEST_TOKEN_SECRET`
3. 查看Superset日志：`docker logs superset_app`

---

## 📞 技术支持

遇到问题？请查看：
- **文档**: `docs/README.md`
- **FAQ**: `docs/FAQ.md`
- **Issue**: GitHub Issues

---

**部署完成后，请访问**: http://localhost:5173

祝您使用愉快！🎉

