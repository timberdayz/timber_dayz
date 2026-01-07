# 🚀 西虹ERP系统部署指南

**版本**: v4.1.0 (方案B+ 扁平化架构)  
**更新时间**: 2025-10-25  
**适用环境**: 开发/测试/生产

---

## 📋 系统要求

### 硬件要求

**最低配置**:
- CPU: 2核心
- 内存: 4GB
- 硬盘: 20GB

**推荐配置**:
- CPU: 4核心+
- 内存: 8GB+
- 硬盘: 50GB+
- SSD存储（提升数据库性能）

### 软件要求

**必需**:
- Python 3.10+
- Node.js 16+
- PostgreSQL 15+（或Docker）
- Git

**可选**:
- Redis 7+（缓存加速）
- Docker Desktop（容器化部署）

---

## 📦 安装步骤

### 方式1：标准安装（本地开发）

#### Step 1: 克隆代码

```bash
git clone <repository_url>
cd xihong_erp
```

#### Step 2: 安装Python依赖

```bash
pip install -r requirements.txt
```

#### Step 3: 安装前端依赖

```bash
cd frontend
npm install
cd ..
```

#### Step 4: 配置环境变量

```bash
# 复制环境变量模板
copy env.example .env

# 编辑.env配置数据库连接
DATABASE_URL=postgresql://erp_user:erp_pass_2025@localhost:5432/xihong_erp
```

#### Step 5: 启动PostgreSQL

**方式A: Docker**
```bash
docker-compose up -d postgres
```

**方式B: 本地安装**
```bash
# Windows
net start postgresql-x64-15

# Linux
sudo systemctl start postgresql
```

#### Step 6: 初始化数据库

```bash
# 数据库已通过方案B+重建，无需迁移
# 验证表结构
python scripts/check_db_schema.py
```

#### Step 7: 启动系统

```bash
python run.py
```

### 方式2: Docker部署（推荐生产环境）

#### Step 1: 配置docker-compose.yml

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    container_name: xihong_erp_postgres
    environment:
      POSTGRES_USER: erp_user
      POSTGRES_PASSWORD: erp_pass_2025
      POSTGRES_DB: xihong_erp
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U erp_user"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    container_name: xihong_erp_backend
    ports:
      - "8001:8001"
    environment:
      DATABASE_URL: postgresql://erp_user:erp_pass_2025@postgres:5432/xihong_erp
    depends_on:
      - postgres

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.prod
    container_name: xihong_erp_frontend
    ports:
      - "5173:80"
    depends_on:
      - backend

volumes:
  postgres_data:
```

#### Step 2: 构建和启动

```bash
# 构建镜像
docker-compose build

# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 查看状态
docker-compose ps
```

---

## 🔧 配置说明

### 环境变量配置

**数据库配置**:
```bash
DATABASE_URL=postgresql://用户名:密码@主机:端口/数据库名
# 示例（本地）:
DATABASE_URL=postgresql://erp_user:erp_pass_2025@localhost:5432/xihong_erp

# 示例（Docker）:
DATABASE_URL=postgresql://erp_user:erp_pass_2025@postgres:5432/xihong_erp
```

**Redis配置**（可选）:
```bash
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=  # 留空表示无密码
```

**JWT配置**:
```bash
JWT_SECRET_KEY=your-super-secret-key-change-in-production
JWT_EXPIRE_MINUTES=1440  # 24小时
```

### 数据库连接池配置

**backend/utils/config.py**:
```python
DB_POOL_SIZE=5          # 连接池大小
DB_MAX_OVERFLOW=10      # 最大溢出连接
DB_POOL_TIMEOUT=30      # 连接超时（秒）
DB_POOL_RECYCLE=3600    # 连接回收时间（秒）
```

---

## ✅ 部署验证

### 验证数据库

```bash
# 检查表结构
python scripts/check_db_schema.py

# 验证数据
python scripts/test_database_write.py
```

### 验证后端

```bash
# 诊断连接
python scripts/diagnose_backend.py

# 测试API
python scripts/test_field_mapping_api.py
```

### 验证前端

```bash
# 访问浏览器
http://localhost:5173

# 检查：
- 前端界面正常加载
- 左侧菜单显示完整
- 版本号正确（v4.0.0）
```

---

## 🐛 故障排查

### 问题1: 数据库连接失败

**症状**: `could not connect to server`

**检查**:
```bash
# Docker环境
docker ps | findstr postgres

# 本地环境  
sc query postgresql-x64-15
```

**解决**:
```bash
# 启动PostgreSQL容器
docker start xihong_erp_postgres

# 或启动本地服务
net start postgresql-x64-15
```

### 问题2: 端口占用

**症状**: `Address already in use`

**检查**:
```bash
netstat -ano | findstr 8001
netstat -ano | findstr 5173
```

**解决**:
```bash
# 停止占用进程
taskkill /F /PID <进程ID>

# 或更改端口
python run.py  # 使用不同端口
```

### 问题3: 前端API超时

**症状**: `timeout of 30000ms exceeded`

**状态**: 已知问题，记录在`docs/KNOWN_ISSUES.md`

**临时方案**:
1. 等待后端完全启动（2-3分钟）
2. 刷新页面重试
3. 检查后端日志

**完整解决**: 参见`docs/DEEP_DIAGNOSIS_REPORT.md`

---

## 🔒 生产环境配置

### 安全加固

1. **更改默认密码**:
```bash
# PostgreSQL
ALTER USER erp_user WITH PASSWORD 'strong_password_here';

# JWT Secret
JWT_SECRET_KEY=<32位随机字符串>
```

2. **启用HTTPS**:
```bash
# 使用Nginx反向代理
# 配置SSL证书
```

3. **限制CORS**:
```python
# backend/main.py
allow_origins=["https://yourdomain.com"]  # 只允许特定域名
```

4. **启用认证**:
```python
# 取消注释路由的dependencies=[Depends(get_current_user)]
```

### 性能优化

1. **启用Redis缓存**:
```bash
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

2. **增加Worker数量**:
```bash
uvicorn backend.main:app --workers 4 --host 0.0.0.0 --port 8001
```

3. **PostgreSQL优化**:
```sql
-- 增加连接数
ALTER SYSTEM SET max_connections = 200;

-- 优化查询
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';
```

---

## 📊 监控和维护

### 日志位置

```
后端日志: backend/logs/*.log
前端日志: 浏览器控制台（F12）
数据库日志: PostgreSQL日志目录
```

### 数据备份

```bash
# 备份PostgreSQL
pg_dump -h localhost -U erp_user -d xihong_erp > backup_$(date +%Y%m%d).sql

# 备份文件
tar -czf data_backup_$(date +%Y%m%d).tar.gz data/
```

### 定期维护

```sql
-- PostgreSQL优化（每周）
VACUUM ANALYZE;

-- 重建索引（每月）
REINDEX DATABASE xihong_erp;
```

---

## 🎯 快速命令参考

### 开发环境

```bash
# 启动所有服务
python run.py

# 仅后端
python run.py --backend-only

# 仅前端  
python run.py --frontend-only

# 测试
python scripts/test_e2e_complete.py
```

### Docker环境

```bash
# 启动
docker-compose up -d

# 停止
docker-compose down

# 重启
docker-compose restart

# 查看日志
docker-compose logs -f backend
```

### 数据库操作

```bash
# 连接数据库
psql -h localhost -U erp_user -d xihong_erp

# 查看表
\dt

# 查询
SELECT COUNT(*) FROM catalog_files;
```

---

## 📞 技术支持

### 文档资源

- **快速开始**: `START_HERE_FINAL.md`
- **用户指南**: `docs/QUICK_USER_GUIDE.md`
- **已知问题**: `docs/KNOWN_ISSUES.md`
- **API文档**: http://localhost:8001/api/docs

### 问题反馈

如遇到问题，请查阅：
1. `docs/KNOWN_ISSUES.md` - 已知问题和解决方案
2. `docs/DEEP_DIAGNOSIS_REPORT.md` - 深度诊断报告
3. 项目Issues区 - 提交问题

---

**部署完成后，系统即可投入使用！** ✅

**如有问题，请参考troubleshooting章节或查阅技术文档。**

