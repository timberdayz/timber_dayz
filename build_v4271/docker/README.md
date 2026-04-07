# 🐳 西虹ERP系统 - Docker部署

> **一键部署，云端迁移零成本**

---

## 🚀 快速开始

### Windows用户

```bash
# 开发环境（仅数据库）
docker\scripts\start-dev.bat

# 生产环境（完整系统）
docker\scripts\start-prod.bat

# 停止服务
docker\scripts\stop.bat
```

### Linux/Mac用户

```bash
# 添加执行权限
chmod +x scripts/*.sh

# 开发环境（仅数据库）
./scripts/start-dev.sh

# 生产环境（完整系统）
./scripts/start-prod.sh

# 健康检查
./scripts/health-check.sh

# 停止服务
./scripts/stop.sh

# 或使用Makefile
cd ..
make dev      # 开发环境
make prod     # 生产环境
make health   # 健康检查
make stop     # 停止服务
```

---

## 📁 目录结构

```
docker/
├── scripts/                    # 启动和管理脚本
│   ├── start-dev.sh/.bat      # 开发环境启动
│   ├── start-prod.sh/.bat     # 生产环境启动
│   ├── stop.sh/.bat           # 停止脚本
│   └── health-check.sh        # 健康检查
├── postgres/                   # PostgreSQL配置
│   ├── init.sql              # 数据库初始化SQL
│   └── init-tables.py        # 表结构初始化
├── nginx/                      # Nginx配置
│   └── default.conf          # 反向代理配置
└── README.md                   # 本文件
```

---

## 🎯 部署模式

### 开发模式
- PostgreSQL数据库
- pgAdmin管理界面
- 后端和前端本地运行

### 生产模式
- PostgreSQL数据库
- FastAPI后端（容器化）
- Vue.js前端（容器化）
- Nginx反向代理

---

## 📊 服务访问

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端 | http://localhost:5174 | Vue.js界面 |
| 后端API | http://localhost:8001 | FastAPI |
| API文档 | http://localhost:8001/api/docs | Swagger UI |
| PostgreSQL | localhost:5432 | 数据库 |
| pgAdmin | http://localhost:5051 | 数据库管理 |

---

## 🔐 默认账号

### pgAdmin
- 邮箱: `dev@xihong.com` (开发) / `admin@xihong.com` (生产)
- 密码: `dev123` (开发) / `admin` (生产)

### PostgreSQL
- 用户名: `erp_dev` (开发) / `erp_user` (生产)
- 密码: `dev_pass_2025` (开发) / `erp_pass_2025` (生产)
- 数据库: `xihong_erp_dev` (开发) / `xihong_erp` (生产)

⚠️ **生产环境必须修改默认密码！**

---

## ⚙️ 常用命令

### 服务管理

```bash
# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f
docker-compose logs -f backend    # 后端日志
docker-compose logs -f postgres   # 数据库日志

# 重启服务
docker-compose restart
docker-compose restart backend    # 重启后端

# 停止服务
docker-compose down               # 停止并删除容器
docker-compose down -v            # 停止并删除数据卷
```

### 数据库操作

```bash
# 进入数据库
docker-compose exec postgres psql -U erp_user -d xihong_erp

# 备份数据库
docker-compose exec -T postgres pg_dump -U erp_user xihong_erp > backup.sql

# 恢复数据库
docker-compose exec -T postgres psql -U erp_user -d xihong_erp < backup.sql

# 初始化数据库表
python postgres/init-tables.py
```

### 容器操作

```bash
# 进入后端容器
docker-compose exec backend /bin/bash

# 进入前端容器
docker-compose exec frontend /bin/sh

# 查看资源使用
docker stats
```

---

## 🔧 故障排除

### 端口被占用

```bash
# Windows
netstat -ano | findstr :5432
taskkill /PID <PID> /F

# Linux/Mac
lsof -i:5432
kill -9 <PID>

# 或修改.env文件中的端口配置
POSTGRES_PORT=5433
```

### 容器无法启动

```bash
# 查看日志
docker-compose logs <service-name>

# 重新构建
docker-compose build --no-cache

# 清理并重启
docker-compose down
docker system prune -a
docker-compose up -d
```

### 数据库连接失败

```bash
# 检查数据库状态
docker-compose exec postgres pg_isready -U erp_user -d xihong_erp

# 查看数据库日志
docker-compose logs postgres

# 重启数据库
docker-compose restart postgres
```

---

## 📚 完整文档

- **[Docker部署指南](../docs/DOCKER_DEPLOYMENT.md)** - 完整部署文档
- **[Docker验证清单](../docs/DOCKER_CHECKLIST.md)** - 部署验证步骤
- **[主README](../README.md)** - 项目说明

---

## 🆘 获取帮助

1. 查看日志: `docker-compose logs -f`
2. 健康检查: `./scripts/health-check.sh`
3. 查阅文档: `../docs/DOCKER_DEPLOYMENT.md`
4. 提交Issue: 项目仓库

---

**最后更新**: 2025-10-23  
**维护者**: 西虹ERP团队

