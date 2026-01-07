# 🚀 重启后快速指南

> **重启电脑后看这里** | **新对话开始前看这里**  
> **5分钟快速上手** | **版本 v4.1.0**

---

## 📌 核心信息

### 系统架构
- **数据库**: PostgreSQL (Docker容器)
- **后端**: FastAPI + Python 3.11+
- **前端**: Vue.js 3 + Element Plus
- **开发模式**: 混合架构（Docker数据库 + 本地代码）

### 关键文件位置
```
项目根目录: F:\Vscode\python_programme\AI_code\xihong_erp\

启动脚本:
├── start-docker-dev.bat         ← 启动Docker数据库
├── start-docker-prod.bat        ← 启动全部Docker服务
└── stop-local-postgres.bat      ← 停止本地PostgreSQL

开发目录:
├── backend/                     ← 后端代码
├── frontend/                    ← 前端代码
└── modules/                     ← 业务模块（数据采集等）

文档目录:
└── docs/
    ├── DOCKER_QUICK_START.md    ← Docker详细指南
    ├── DEVELOPMENT_WORKFLOW.md  ← 开发工作流
    └── RESTART_CHECKLIST.md     ← 完整检查清单
```

---

## ⚡ 3步快速启动

### 步骤1: 启动Docker（1分钟）

```bash
# 双击运行或在项目根目录执行
start-docker-dev.bat

# 等待看到：
# ✔ Container postgres  Started
# ✔ Container pgadmin   Started
```

### 步骤2: 启动后端（1分钟）

```bash
# 新开终端
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 步骤3: 启动前端（1分钟）

```bash
# 再开一个终端
cd frontend
npm run dev
```

✅ **完成！** 现在可以访问：
- 前端: http://localhost:5173
- 后端API: http://localhost:8000/docs
- 数据库管理: http://localhost:5051

---

## 🔥 常见问题快速修复

### ❌ Docker未启动
```bash
# 启动Docker Desktop
# 等待任务栏图标变绿
```

### ❌ 端口5432被占用
```bash
# 停止本地PostgreSQL
stop-local-postgres.bat
```

### ❌ 数据库连接失败
```bash
# 重启Docker容器
docker-compose restart postgres
```

### ❌ 前端/后端依赖问题
```bash
# 前端
cd frontend
npm install

# 后端
cd backend
pip install -r requirements.txt
```

---

## 📚 详细文档链接

- **[Docker快速启动指南](docs/DOCKER_QUICK_START.md)** - Docker完整使用说明
- **[开发工作流指南](docs/DEVELOPMENT_WORKFLOW.md)** - 后端/前端/字段映射开发
- **[重启检查清单](docs/RESTART_CHECKLIST.md)** - 详细的检查步骤

---

## 🎯 下一步开发

根据您的计划，当前任务优先级：

1. ✅ **后端API开发** - 已完成基础架构
2. ✅ **字段映射系统** - 已完成核心功能
3. ⏭️ **前端界面优化** - 待开始
4. ⏭️ **数据采集模块修复** - 最后处理

**新对话建议开始内容**：
- "我已经重启完成，按照RESTART_GUIDE.md启动了所有服务，现在要开始优化前端界面"
- "我已经按照指南启动了Docker和后端，现在要继续开发字段映射系统"

---

## 💾 数据库信息

### pgAdmin登录
- 地址: http://localhost:5051
- 邮箱: admin@xihongerp.com
- 密码: admin123

### PostgreSQL连接
- 主机: localhost (本地) 或 postgres (Docker内部)
- 端口: 5432
- 数据库: xihong_erp
- 用户: erp_user
- 密码: erp_pass_2025

### 数据库表
系统已自动创建16个表：
- 维度表: dim_platform, dim_shop, dim_product
- 事实表: fact_sales_orders, fact_product_metrics
- 暂存表: staging_orders, staging_product_metrics
- 管理表: catalog_files, accounts, data_records
- 等等...

---

## 🛠️ 开发模式选择

### 模式A: 混合模式（推荐）✅
- Docker: 仅数据库
- 本地: 后端 + 前端
- **优点**: 代码热重载，调试方便

### 模式B: 纯Docker模式
- Docker: 全部服务
- **优点**: 接近生产环境

**命令对比**:
```bash
# 模式A（推荐）
start-docker-dev.bat           # 只启动数据库
cd backend && uvicorn main:app --reload
cd frontend && npm run dev

# 模式B
start-docker-prod.bat          # 启动全部服务
```

---

## 📊 系统状态检查

### 快速检查命令
```bash
# 检查Docker容器
docker-compose ps

# 检查后端健康
curl http://localhost:8000/health

# 检查数据库表
docker-compose exec postgres psql -U erp_user -d xihong_erp -c "\dt"
```

### 期望输出
```
✅ postgres   running (healthy)
✅ pgadmin    running (healthy)
✅ backend    http://localhost:8000 (200 OK)
✅ frontend   http://localhost:5173 (可访问)
✅ database   16 tables created
```

---

## 🎬 生产环境部署

### 24小时运行配置
```bash
# 1. 启动生产模式
start-docker-prod.bat

# 2. 配置自动重启
# 已在docker-compose.prod.yml配置：
# restart: unless-stopped

# 3. 数据持久化
# 数据会自动保存到Docker卷

# 4. 定期备份
# 每天自动备份数据库（建议设置定时任务）
docker-compose exec -T postgres pg_dump -U erp_user xihong_erp > backup.sql
```

### 云服务器部署
```bash
# 1. 上传代码到服务器
git clone <your-repo>

# 2. 配置环境变量
cp env.production.example .env
nano .env  # 修改密码等配置

# 3. 一键部署
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 4. 验证
curl http://your-server-ip:8000/health
```

---

## 🆘 紧急联系

如果遇到严重问题：

1. **停止所有服务**
   ```bash
   docker-compose down
   ```

2. **清理并重启**
   ```bash
   docker-compose down -v  # 警告：会删除数据！
   docker-compose up -d --build
   ```

3. **查看详细日志**
   ```bash
   docker-compose logs -f
   ```

4. **恢复数据库备份**
   ```bash
   cat backup.sql | docker-compose exec -T postgres psql -U erp_user -d xihong_erp
   ```

---

**准备好了吗？开始新的开发之旅！** 🚀

```bash
# 执行启动命令
start-docker-dev.bat

# 新对话中告诉AI
"我已经按照RESTART_GUIDE.md完成了启动，现在要继续开发工作"
```

