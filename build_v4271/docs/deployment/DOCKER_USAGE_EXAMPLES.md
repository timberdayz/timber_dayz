# Docker使用示例

> **实际场景的Docker使用案例**

---

## 📋 目录

- [开发者日常工作流](#开发者日常工作流)
- [团队协作场景](#团队协作场景)
- [生产部署场景](#生产部署场景)
- [故障恢复场景](#故障恢复场景)
- [性能优化场景](#性能优化场景)

---

## 👨‍💻 开发者日常工作流

### 场景1：新员工入职第一天

**小张刚加入团队，需要快速搭建开发环境**

```bash
# Day 1 - 上午9:00

# 1. 克隆代码
git clone https://github.com/your-company/xihong_erp.git
cd xihong_erp

# 2. 检查环境（2分钟）
# Windows
docker\scripts\check-requirements.bat

# Linux/Mac
chmod +x docker/scripts/*.sh
./docker/scripts/check-requirements.sh

# 3. 启动数据库（3分钟）
# Windows
docker\scripts\start-dev.bat

# Linux/Mac
make dev

# 4. 本地运行代码
# Terminal 1 - 后端
cd backend
pip install -r requirements.txt
uvicorn main:app --reload

# Terminal 2 - 前端
cd frontend
npm install
npm run dev

# 完成！小张9:10就开始写代码了 🎉
```

---

### 场景2：修复Bug需要测试

**小李需要修复一个数据库相关的Bug**

```bash
# 1. 确保数据库运行
docker-compose ps postgres

# 2. 如果没运行，启动它
make dev

# 3. 查看数据库日志
docker-compose logs -f postgres

# 4. 进入数据库调试
docker-compose exec postgres psql -U erp_user -d xihong_erp

# 5. 修改代码后重启后端
# 代码会自动重载（--reload）

# 6. 测试完成后提交
git add .
git commit -m "fix: 修复数据库连接问题"
git push
```

---

### 场景3：需要清空数据库重新开始

**小王搞乱了测试数据，需要重置**

```bash
# 方式1：删除数据卷重新创建
docker-compose down -v
make dev

# 方式2：手动清空表
docker-compose exec postgres psql -U erp_user -d xihong_erp
# 在psql中：
DROP TABLE IF EXISTS accounts CASCADE;
# 然后重新初始化
python docker/postgres/init-tables.py

# 方式3：使用备份恢复
docker-compose exec -T postgres psql -U erp_user -d xihong_erp < backups/clean_db.sql
```

---

## 👥 团队协作场景

### 场景4：多人同时开发不同功能

**团队有5个人，每人开发不同模块**

```bash
# 团队成员A - 开发后端API
cd xihong_erp
make dev                          # 启动数据库
cd backend
uvicorn main:app --reload --port 8000

# 团队成员B - 开发前端界面
cd xihong_erp
make dev                          # 启动数据库
cd frontend
npm run dev                       # 端口5173

# 团队成员C - 开发数据采集模块
cd xihong_erp
make dev                          # 启动数据库
python run_new.py                 # 运行CLI模式

# 团队成员D - 测试完整系统
cd xihong_erp
make prod                         # 启动完整Docker环境
# 访问 http://localhost:5174

# 团队成员E - 数据库管理
cd xihong_erp
make dev
# 访问 pgAdmin http://localhost:5051
```

**关键点**：
- ✅ 每个人只需要一个命令就能启动数据库
- ✅ 数据库端口统一（5432），所有人数据一致
- ✅ 各自的前后端端口不冲突

---

### 场景5：代码评审需要查看PR效果

**技术Leader需要查看PR的实际效果**

```bash
# 1. 切换到PR分支
git fetch origin pull/123/head:pr-123
git checkout pr-123

# 2. 启动完整系统查看效果
make prod

# 3. 访问前端查看
# http://localhost:5174

# 4. 检查API变更
# http://localhost:8001/api/docs

# 5. 查看日志确认无错误
make logs

# 6. 评审完成，切回主分支
git checkout main
make stop
```

---

## 🚀 生产部署场景

### 场景6：第一次部署到阿里云

**运维工程师小陈第一次部署系统到云端**

```bash
# === 在阿里云ECS上 ===

# 1. 安装Docker
curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun
systemctl start docker
systemctl enable docker

# 2. 安装Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 3. 克隆代码
git clone https://your-company/xihong_erp.git
cd xihong_erp

# 4. 配置生产环境
cp env.production.example .env
nano .env

# 修改：
# POSTGRES_PASSWORD=生成的强密码
# SECRET_KEY=生成的随机字符串
# ALLOWED_ORIGINS=https://your-domain.com

# 5. 启动生产环境
./docker/scripts/start-prod.sh

# 6. 配置Nginx反向代理（可选）
sudo apt install nginx
sudo nano /etc/nginx/sites-available/xihong-erp

# 7. 配置SSL证书
sudo certbot --nginx -d your-domain.com

# 8. 完成！访问 https://your-domain.com
```

---

### 场景7：版本更新部署

**需要更新系统到最新版本**

```bash
# 1. 备份当前数据
./docker/scripts/stop.sh --backup
# 或
make db-backup

# 2. 拉取最新代码
git pull origin main

# 3. 重新构建镜像
make build

# 4. 重启服务
make prod

# 5. 健康检查
make health

# 6. 查看日志确认无误
make logs

# 如果有问题，回滚：
git checkout <previous-version>
make build
make prod
```

---

### 场景8：扩展到多实例负载均衡

**访问量增加，需要扩展后端实例**

```bash
# 编辑 docker-compose.prod.yml
backend:
  deploy:
    replicas: 3  # 从1改为3

# 重新部署
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 查看状态
docker-compose ps

# 应该看到3个backend实例：
# xihong_erp_backend_1
# xihong_erp_backend_2
# xihong_erp_backend_3

# Nginx会自动负载均衡到这3个实例
```

---

## 🔧 故障恢复场景

### 场景9：数据库崩溃需要恢复

**数据库容器崩溃，需要从备份恢复**

```bash
# 1. 停止所有服务
make stop

# 2. 删除损坏的数据卷
docker volume rm xihong_erp_postgres_data

# 3. 重新启动数据库
docker-compose up -d postgres

# 4. 等待数据库就绪
docker-compose exec postgres pg_isready -U erp_user

# 5. 恢复备份
docker-compose exec -T postgres psql -U erp_user -d xihong_erp < backups/postgres_20251023.sql

# 6. 验证数据
docker-compose exec postgres psql -U erp_user -d xihong_erp -c "SELECT COUNT(*) FROM accounts;"

# 7. 重启所有服务
make prod
```

---

### 场景10：容器内存不足被杀

**后端容器因OOM被杀**

```bash
# 1. 查看容器日志
docker-compose logs backend | grep -i "killed\|oom"

# 2. 增加内存限制
# 编辑 docker-compose.yml
backend:
  deploy:
    resources:
      limits:
        memory: 4G  # 从2G增加到4G

# 3. 重启服务
docker-compose restart backend

# 4. 监控内存使用
docker stats backend

# 5. 如果还不够，考虑优化代码或增加实例
```

---

### 场景11：端口冲突无法启动

**5432端口被占用**

```bash
# 1. 找到占用端口的进程
# Windows
netstat -ano | findstr :5432
# 记录PID

taskkill /PID <PID> /F

# Linux
lsof -i:5432
# 或
kill -9 <PID>

# 2. 或者修改端口
# 编辑 .env
POSTGRES_PORT=5433

# 3. 重新启动
make dev
```

---

## ⚡ 性能优化场景

### 场景12：优化PostgreSQL性能

**数据量增大，查询变慢**

```bash
# 1. 连接数据库
docker-compose exec postgres psql -U erp_user -d xihong_erp

# 2. 执行优化命令
VACUUM ANALYZE;

# 3. 创建缺失的索引
CREATE INDEX idx_orders_date ON orders(order_date);
CREATE INDEX idx_products_sku ON products(sku);

# 4. 调整数据库配置
ALTER SYSTEM SET shared_buffers = '512MB';
ALTER SYSTEM SET work_mem = '32MB';
ALTER SYSTEM SET effective_cache_size = '2GB';

# 5. 重启数据库应用配置
docker-compose restart postgres

# 6. 验证性能提升
EXPLAIN ANALYZE SELECT * FROM orders WHERE order_date > '2025-01-01';
```

---

### 场景13：前端静态资源优化

**前端加载慢，需要优化**

```bash
# 1. 启用Gzip压缩（已在Nginx配置中）
# docker/nginx/default.conf 已配置

# 2. 启用缓存（已在Nginx配置中）
# 静态资源缓存1年

# 3. 构建生产版本
cd frontend
npm run build

# 4. 查看构建产物大小
ls -lh dist/

# 5. 使用Docker多阶段构建（已实现）
# Dockerfile.frontend 已优化

# 6. 重新构建前端镜像
docker build -f Dockerfile.frontend -t xihong-erp-frontend:latest .

# 7. 重启前端服务
docker-compose restart frontend
```

---

## 📚 总结

### 常用命令速查

```bash
# 开发环境
make dev          # 启动开发环境
make stop         # 停止服务
make logs         # 查看日志
make db-backup    # 备份数据库

# 生产环境
make prod         # 启动生产环境
make health       # 健康检查
make restart      # 重启服务
make build        # 构建镜像

# 故障排除
make logs         # 查看所有日志
docker-compose ps # 查看服务状态
docker stats      # 查看资源使用
make db-shell     # 进入数据库
```

### 最佳实践

1. **开发环境**：只启动数据库，代码本地运行（热重载）
2. **测试环境**：完整Docker环境，测试集成
3. **生产环境**：完整Docker环境，配置资源限制
4. **定期备份**：每天自动备份数据库
5. **监控日志**：定期查看错误日志
6. **性能监控**：使用`docker stats`监控资源

---

**更多场景持续更新中...** 🚀

