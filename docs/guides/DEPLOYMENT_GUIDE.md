# 部署指南

**版本**: v4.0.0 混合架构  
**更新日期**: 2025-10-21  

## ⚠️ 重要更新 - v4.0.0混合架构

本指南已更新到最新的混合架构部署方式：
- ✅ 统一启动脚本 `run.py`
- ✅ FastAPI统一后端
- ✅ Vue.js统一前端
- ✅ 完整保留数据采集模块

---

## 📋 目录

- [环境要求](#环境要求)
- [Docker部署](#docker部署-推荐)
- [本地部署](#本地部署)
- [生产环境配置](#生产环境配置)
- [监控与维护](#监控与维护)

---

## 环境要求

### 最低配置

| 项目 | 要求 |
|------|------|
| 操作系统 | Linux/Windows/macOS |
| Python | >= 3.10 |
| 内存 | >= 4GB |
| 磁盘 | >= 10GB |
| 数据库 | SQLite或PostgreSQL |

### 推荐配置（生产环境）

| 项目 | 推荐 |
|------|------|
| 操作系统 | Ubuntu 20.04+ / CentOS 8+ |
| Python | 3.11 |
| 内存 | >= 8GB |
| 磁盘 | >= 50GB SSD |
| 数据库 | PostgreSQL 15+ |
| CPU | >= 4核 |

---

## Docker部署（推荐）

### 快速开始

#### 1. 克隆代码

```bash
git clone https://github.com/your-repo/xihong_erp.git
cd xihong_erp
```

#### 2. 配置环境变量

```bash
# 复制环境变量模板
cp env.example .env

# 编辑.env文件
nano .env
```

#### 3. 构建并启动

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f erp-frontend
```

#### 4. 访问系统

打开浏览器访问: `http://localhost:8501`

---

### Docker Compose配置说明

#### 服务组成

| 服务 | 说明 | 端口 |
|------|------|------|
| erp-frontend | Streamlit前端 | 8501 |
| erp-etl-worker | ETL后台任务 | - |
| postgres | PostgreSQL数据库 | 5432 |

#### 启动模式

**开发模式（仅前端）**:
```bash
docker-compose up erp-frontend
```

**生产模式（前端+ETL+PostgreSQL）**:
```bash
docker-compose --profile production up -d
```

**仅ETL Worker**:
```bash
docker-compose up erp-etl-worker
```

---

### 数据持久化

#### 卷挂载

```yaml
volumes:
  - ./data:/app/data          # 数据库文件
  - ./temp:/app/temp          # 临时文件
  - ./logs:/app/logs          # 日志文件
  - ./backups:/app/backups    # 备份文件
  - ./config:/app/config      # 配置文件
```

#### 备份数据

```bash
# 备份所有数据卷
docker run --rm \
  -v $(pwd)/data:/data \
  -v $(pwd)/backups:/backups \
  alpine tar czf /backups/backup_$(date +%Y%m%d).tar.gz /data

# 恢复备份
tar xzf backups/backup_20241016.tar.gz -C ./
```

---

### 常用Docker命令

```bash
# 查看运行状态
docker-compose ps

# 查看日志
docker-compose logs -f erp-frontend
docker-compose logs -f erp-etl-worker

# 重启服务
docker-compose restart erp-frontend

# 停止服务
docker-compose down

# 完全清理（包括卷）
docker-compose down -v

# 进入容器
docker-compose exec erp-frontend /bin/bash

# 更新代码
git pull
docker-compose build
docker-compose up -d
```

---

## 本地部署

### 安装步骤

#### 1. 安装Python

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install python3.11 python3.11-venv python3-pip

# macOS
brew install python@3.11

# Windows
# 下载安装包：https://www.python.org/downloads/
```

#### 2. 创建虚拟环境

```bash
# 创建虚拟环境
python3.11 -m venv venv

# 激活虚拟环境
# Linux/macOS:
source venv/bin/activate

# Windows:
venv\Scripts\activate
```

#### 3. 安装依赖

```bash
pip install -r requirements.txt
```

#### 4. 初始化数据库

```bash
# 运行Alembic迁移
python -m alembic upgrade head
```

#### 5. 启动服务

```bash
# 启动Streamlit
streamlit run frontend_streamlit/main.py
```

---

### 手动配置

#### 配置文件位置

```
config/
├── database/
│   └── database.yaml        # 数据库配置
├── field_mappings.yaml      # 字段映射
└── collectors/              # 采集器配置
```

#### 数据库初始化

```bash
# 方式1：使用Alembic
python -m alembic upgrade head

# 方式2：手动创建表
python -c "
from modules.core.db.schema import Base
from sqlalchemy import create_engine
engine = create_engine('sqlite:///data/unified_erp_system.db')
Base.metadata.create_all(engine)
print('数据库表创建完成')
"
```

---

## 生产环境配置

### PostgreSQL配置

#### 1. 安装PostgreSQL

```bash
# Ubuntu
sudo apt-get install postgresql-15

# 启动服务
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

#### 2. 创建数据库和用户

```sql
-- 登录PostgreSQL
sudo -u postgres psql

-- 创建用户
CREATE USER erp_user WITH PASSWORD 'your_secure_password';

-- 创建数据库
CREATE DATABASE erp_db OWNER erp_user;

-- 授权
GRANT ALL PRIVILEGES ON DATABASE erp_db TO erp_user;
```

#### 3. 配置环境变量

```bash
export DATABASE_URL=postgresql://erp_user:your_password@localhost:5432/erp_db
```

#### 4. 运行迁移

```bash
python -m alembic upgrade head
```

---

### Nginx反向代理

#### 配置示例

```nginx
# /etc/nginx/sites-available/erp

server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### 启用配置

```bash
sudo ln -s /etc/nginx/sites-available/erp /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

### Systemd服务

#### 创建服务文件

```ini
# /etc/systemd/system/xihong-erp.service

[Unit]
Description=跨境电商ERP系统
After=network.target postgresql.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/xihong_erp
Environment="DATABASE_URL=postgresql://erp_user:password@localhost/erp_db"
Environment="PYTHONPATH=/opt/xihong_erp"
ExecStart=/opt/xihong_erp/venv/bin/streamlit run frontend_streamlit/main.py --server.port 8501 --server.headless true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### 启动服务

```bash
sudo systemctl daemon-reload
sudo systemctl start xihong-erp
sudo systemctl enable xihong-erp
sudo systemctl status xihong-erp
```

---

## 监控与维护

### 健康检查

```bash
# 使用内置脚本
python health_check.py

# 输出示例
# ✅ Python版本: 3.11.0
# ✅ 数据库连接: OK
# ✅ Alembic版本: 20251016_0004
# ✅ Catalog文件数: 1308
```

### 日志管理

```bash
# 查看Streamlit日志
tail -f logs/streamlit.log

# 查看ETL日志
tail -f logs/etl.log

# 清理旧日志（保留7天）
find logs/ -name "*.log" -mtime +7 -delete
```

### 性能监控

```bash
# 数据库大小
du -h data/unified_erp_system.db

# 缓存大小
du -h temp/cache/

# Catalog状态
python scripts/etl_cli.py status --detail
```

### 定期维护

#### 每天

```bash
# 执行ETL
python scripts/etl_cli.py run temp/outputs

# 检查失败文件
python scripts/etl_cli.py status --quarantine
```

#### 每周

```bash
# 清理旧catalog记录
python scripts/etl_cli.py cleanup --days 30

# 备份数据库
cp data/unified_erp_system.db backups/db_$(date +%Y%m%d).db

# VACUUM数据库
sqlite3 data/unified_erp_system.db "VACUUM; ANALYZE;"
```

#### 每月

```bash
# 清理旧备份（保留3个月）
find backups/ -name "db_*.db" -mtime +90 -delete

# 清理旧日志
find logs/ -name "*.zip" -mtime +90 -delete

# 性能优化检查
python -m alembic current  # 确认在最新版本
```

---

## 🔒 安全配置

### 1. 数据库安全

```bash
# 设置数据库文件权限
chmod 600 data/unified_erp_system.db

# PostgreSQL加密连接
DATABASE_URL=postgresql://user:pwd@localhost/db?sslmode=require
```

### 2. 文件权限

```bash
# 设置目录权限
chmod 755 data/ temp/ logs/ backups/
chmod 600 config/*.yaml
chmod 600 local_accounts.py
```

### 3. 防火墙

```bash
# 只允许本地访问（开发）
firewall-cmd --add-rich-rule='rule family="ipv4" source address="127.0.0.1" port port="8501" protocol="tcp" accept'

# 允许特定IP访问（生产）
firewall-cmd --add-rich-rule='rule family="ipv4" source address="your_ip" port port="8501" protocol="tcp" accept'
```

---

## 🚀 快速部署脚本

### 一键部署（Ubuntu）

```bash
#!/bin/bash
# deploy.sh

set -e

echo "开始部署跨境电商ERP系统..."

# 1. 安装依赖
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3-pip nginx

# 2. 创建用户
sudo useradd -m -s /bin/bash erp

# 3. 克隆代码
sudo -u erp git clone https://github.com/your-repo/xihong_erp.git /home/erp/app
cd /home/erp/app

# 4. 创建虚拟环境
sudo -u erp python3.11 -m venv venv
sudo -u erp ./venv/bin/pip install -r requirements.txt

# 5. 初始化数据库
sudo -u erp ./venv/bin/python -m alembic upgrade head

# 6. 配置Systemd
sudo cp deploy/xihong-erp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start xihong-erp
sudo systemctl enable xihong-erp

# 7. 配置Nginx
sudo cp deploy/nginx.conf /etc/nginx/sites-available/erp
sudo ln -s /etc/nginx/sites-available/erp /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

echo "部署完成！"
echo "访问: http://your-domain.com"
```

---

## 📝 部署检查清单

### 部署前

- [ ] 备份现有数据
- [ ] 准备环境变量配置
- [ ] 确认服务器资源充足
- [ ] 测试数据库连接
- [ ] 准备账号配置文件

### 部署时

- [ ] 克隆代码
- [ ] 安装依赖
- [ ] 配置环境变量
- [ ] 初始化数据库
- [ ] 运行迁移
- [ ] 启动服务
- [ ] 配置反向代理

### 部署后

- [ ] 健康检查通过
- [ ] 访问测试（前端可打开）
- [ ] 功能测试（采集、入库、查询）
- [ ] 性能测试（响应时间<2秒）
- [ ] 配置监控
- [ ] 设置定时备份
- [ ] 文档交付

---

## 🔧 故障恢复

### 服务无法启动

```bash
# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs erp-frontend

# 重启服务
docker-compose restart

# 重建服务
docker-compose down
docker-compose up --build -d
```

### 数据库连接失败

```bash
# 检查数据库文件
ls -lh data/unified_erp_system.db

# 检查权限
chmod 666 data/unified_erp_system.db

# 测试连接
python -c "
from sqlalchemy import create_engine
engine = create_engine('sqlite:///data/unified_erp_system.db')
with engine.connect() as conn:
    result = conn.execute('SELECT 1').scalar()
    print(f'数据库连接正常: {result}')
"
```

---

## 📊 性能优化

### PostgreSQL优化

```sql
-- 创建索引（如果使用PostgreSQL）
CREATE INDEX CONCURRENTLY idx_orders_date 
ON fact_orders(order_date_local);

CREATE INDEX CONCURRENTLY idx_metrics_date 
ON fact_product_metrics(metric_date);

-- 配置shared_buffers
-- 编辑 postgresql.conf
shared_buffers = 256MB
work_mem = 16MB
maintenance_work_mem = 128MB
```

### 缓存优化

```bash
# 增加缓存TTL（生产环境）
# 编辑 modules/services/data_query_service.py
@cached(ttl_seconds=600)  # 从300秒增加到600秒
```

---

**文档维护**: 根据部署经验持续更新  
**最后更新**: 2025-10-16  
**支持**: 查看TROUBLESHOOTING.md获取问题解决方案

