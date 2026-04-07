# 🔄 重启后快速启动检查清单

> **适用场景**: 电脑重启后、新对话开始前  
> **预计时间**: 5-10分钟  
> **版本**: v4.1.0

---

## ✅ 启动前检查（2分钟）

### 1. Docker Desktop 状态

```bash
# Windows: 检查任务栏是否有Docker图标
# 状态应该是绿色的"Docker Desktop is running"

# 命令行验证
docker --version
docker-compose --version
```

✅ **期望输出**:
```
Docker version 24.x.x
Docker Compose version v2.x.x
```

### 2. 本地PostgreSQL服务状态

```bash
# Windows: 检查是否有本地PostgreSQL在运行
netstat -ano | findstr "5432"
```

⚠️ **如果发现5432端口被占用**:
```bash
# 停止本地PostgreSQL（避免端口冲突）
stop-local-postgres.bat
```

### 3. 项目代码状态

```bash
# 切换到项目目录
cd F:\Vscode\python_programme\AI_code\xihong_erp

# 检查Git状态
git status

# 拉取最新代码（如果有团队协作）
git pull
```

---

## 🚀 快速启动流程（3分钟）

### 方式A: 仅开发（推荐）

**使用场景**: 开发后端API、字段映射系统、前端界面

#### 步骤1: 启动Docker数据库（1分钟）

```bash
# 一键启动
start-docker-dev.bat

# 等待启动完成，看到：
# ✔ Container postgres  Started
# ✔ Container pgadmin   Started
```

#### 步骤2: 验证数据库（30秒）

```bash
# 方式1: 访问pgAdmin
http://localhost:5051

# 方式2: 命令行验证
docker-compose ps

# 应该看到2个容器运行中
```

#### 步骤3: 启动后端（1分钟）

```bash
# 新开终端窗口
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 看到以下输出表示成功：
# INFO:     Uvicorn running on http://0.0.0.0:8000
```

#### 步骤4: 启动前端（30秒）

```bash
# 再开一个终端窗口
cd frontend
npm run dev

# 看到以下输出表示成功：
# VITE ready in xxx ms
# ➜  Local:   http://localhost:5173/
```

✅ **启动完成！现在可以开始开发**

**访问地址**:
- 前端: http://localhost:5173
- 后端API: http://localhost:8000/docs
- 数据库: http://localhost:5051

---

### 方式B: 完全Docker模式

**使用场景**: 测试生产环境、演示、不想本地运行代码

```bash
# 一键启动所有服务
start-docker-prod.bat

# 等待5-10分钟（首次需要构建镜像）
```

**访问地址**:
- 前端: http://localhost
- 后端API: http://localhost:8000
- 数据库: http://localhost:5051

---

## 🧪 启动后验证（2分钟）

### 1. 数据库验证

```bash
# 访问 pgAdmin
http://localhost:5051

# 登录
邮箱: admin@xihongerp.com
密码: admin123

# 连接数据库
主机: postgres (Docker内部) 或 localhost (本地)
端口: 5432
数据库: xihong_erp
用户: erp_user
密码: erp_pass_2025

# 展开数据库 → 查看表
# 应该看到16个表
```

### 2. 后端API验证

```bash
# 访问API文档
http://localhost:8000/docs

# 测试健康检查
curl http://localhost:8000/health

# 期望输出
{"status": "healthy", ...}
```

### 3. 前端验证

```bash
# 访问前端
http://localhost:5173

# 检查字段映射界面
http://localhost:5173/field-mapping

# 应该能看到正常的界面
```

---

## 🔧 常见启动问题

### 问题1: Docker Desktop未启动

**症状**: `docker: command not found` 或 `Cannot connect to the Docker daemon`

**解决**:
1. 启动Docker Desktop应用
2. 等待图标变绿
3. 重新运行启动命令

---

### 问题2: 端口冲突

**症状**: `port is already allocated` 或 `bind: address already in use`

**解决**:
```bash
# 检查端口占用
netstat -ano | findstr "5432"
netstat -ano | findstr "5051"
netstat -ano | findstr "8000"

# 停止本地PostgreSQL
stop-local-postgres.bat

# 或停止Docker容器重新启动
docker-compose down
start-docker-dev.bat
```

---

### 问题3: 数据库连接失败

**症状**: 后端启动时报错 `could not connect to server`

**解决**:
```bash
# 1. 检查Docker容器运行
docker-compose ps

# 2. 重启容器
docker-compose restart postgres

# 3. 查看日志
docker-compose logs postgres

# 4. 检查环境变量
cat .env | grep POSTGRES
```

---

### 问题4: 前端依赖问题

**症状**: `npm run dev` 报错 `Module not found`

**解决**:
```bash
cd frontend

# 重新安装依赖
rm -rf node_modules
rm package-lock.json
npm install

# 重新启动
npm run dev
```

---

### 问题5: Python依赖问题

**症状**: 后端启动时报错 `ModuleNotFoundError`

**解决**:
```bash
cd backend

# 重新安装依赖
pip install -r requirements.txt

# 或使用虚拟环境
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

---

## 📋 新对话开始前检查

### 1. 系统状态确认

- [ ] Docker Desktop 运行中（绿色图标）
- [ ] 本地PostgreSQL 已停止（避免端口冲突）
- [ ] 项目代码已更新到最新版本
- [ ] 有足够的磁盘空间（至少5GB）

### 2. 服务启动确认

- [ ] Docker数据库启动成功（`docker-compose ps`）
- [ ] 后端服务启动成功（访问http://localhost:8000/docs）
- [ ] 前端服务启动成功（访问http://localhost:5173）
- [ ] 数据库表已创建（16个表）

### 3. 工具准备

- [ ] VS Code 已打开项目
- [ ] 浏览器已打开开发者工具
- [ ] pgAdmin 已登录数据库
- [ ] Git 状态正常

---

## 🎯 开发模式选择

### 后端开发（字段映射系统）

✅ **推荐配置**:
- Docker: PostgreSQL + pgAdmin
- 本地: 后端服务（uvicorn --reload）
- 本地: 前端服务（npm run dev）

**优点**: 代码修改即生效，调试方便

### 前端开发（界面优化）

✅ **推荐配置**:
- Docker: PostgreSQL + pgAdmin + 后端服务
- 本地: 前端服务（npm run dev）

**优点**: 专注前端，后端稳定运行

### 全栈开发

✅ **推荐配置**:
- Docker: PostgreSQL + pgAdmin
- 本地: 后端服务 + 前端服务

**优点**: 完全控制，最灵活

### 测试/演示

✅ **推荐配置**:
- Docker: 全部服务（start-docker-prod.bat）

**优点**: 接近生产环境

---

## 💡 效率提升技巧

### 1. 使用快捷脚本

创建桌面快捷方式指向：
```
F:\Vscode\python_programme\AI_code\xihong_erp\start-docker-dev.bat
```

### 2. 设置开机自启动

将Docker Desktop添加到开机启动项

### 3. 使用多终端

- 终端1: Docker日志 `docker-compose logs -f`
- 终端2: 后端服务 `uvicorn main:app --reload`
- 终端3: 前端服务 `npm run dev`
- 终端4: Git操作

### 4. 浏览器书签

保存常用地址到书签栏：
- 前端: http://localhost:5173
- 后端API: http://localhost:8000/docs
- pgAdmin: http://localhost:5051

---

## 📞 遇到问题？

1. 查看 [Docker快速启动指南](DOCKER_QUICK_START.md)
2. 查看 [开发工作流指南](DEVELOPMENT_WORKFLOW.md)
3. 检查 Docker 日志: `docker-compose logs -f`
4. 重启所有服务: `docker-compose restart`

---

**准备就绪！开始新的开发对话** 🚀

