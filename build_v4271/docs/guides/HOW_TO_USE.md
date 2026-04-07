# 📖 西虹ERP系统使用指南

## 🚀 快速启动（推荐方式）

### 步骤1: 启动主入口
```bash
cd F:\Vscode\python_programme\AI_code\xihong_erp
python run_new.py
```

### 步骤2: 选择功能模块

你会看到这样的主菜单：
```
🎯 ERP系统主菜单 (新架构)
==================================================
📱 可用应用模块:
  1. ⚪ 账号管理
  2. ⚪ 后端API管理        ← 🆕 管理FastAPI后端
  3. ⚪ 数据采集中心
  4. ⚪ 数据管理中心
  5. ⚪ 前端页面管理      ← 🆕 管理Vue.js前端
  6. ⚪ Vue字段映射审核
  7. ⚪ Web界面管理

🔧 系统管理:
  8. 📊 系统状态
  9. 🔍 健康检查
  10. 🔄 重新发现应用
  0. ❌ 退出系统
```

## 🌐 启动Vue.js前端

### 方式1: 通过主菜单（推荐）

```bash
# 1. 启动主入口
python run_new.py

# 2. 选择 "5" - 前端页面管理

# 3. 进入前端管理菜单后，选择 "1" - 启动前端服务
```

你会看到：
```
🌐 前端页面管理 v1.0.0
========================================
📋 管理Vue.js前端服务，支持启动、停止、重启前端开发服务器
🔗 访问地址: http://localhost:5173
📁 前端目录: F:\...\xihong_erp\frontend
🔘 状态: ⚪ 未运行

🌐 前端管理 - 功能菜单
----------------------------------------
1. 🚀 启动前端服务       ← 选择这个
2. ⏹️  停止前端服务
3. 🔄 重启前端服务
4. 📊 查看运行状态
5. 🌐 在浏览器中打开
0. 🔙 返回主菜单
```

**自动化流程**:
- ✅ 自动检测npm环境
- ✅ 首次运行自动安装依赖
- ✅ 等待3秒确保服务启动
- ✅ 显示访问地址

### 方式2: 独立脚本
```bash
python start_frontend.py
```

### 方式3: 手动启动
```bash
cd frontend
npm install
npm run dev
```

## ⚙️ 启动FastAPI后端

### 方式1: 通过主菜单（推荐）

```bash
# 1. 启动主入口
python run_new.py

# 2. 选择 "2" - 后端API管理

# 3. 进入后端管理菜单后，选择 "1" - 启动后端服务
```

你会看到：
```
⚙️ 后端API管理 v1.0.0
========================================
📋 管理FastAPI后端服务，支持启动、停止、重启API服务器
🔗 API地址: http://localhost:8000
📚 API文档: http://localhost:8000/api/docs
📁 后端目录: F:\...\xihong_erp\backend
🔘 状态: ⚪ 未运行

⚙️ 后端管理 - 功能菜单
----------------------------------------
1. 🚀 启动后端服务       ← 选择这个
2. ⏹️  停止后端服务
3. 🔄 重启后端服务
4. 📊 查看运行状态
5. 📚 打开API文档
6. 🧪 测试API连接
0. 🔙 返回主菜单
```

**自动化流程**:
- ✅ 自动检测Python环境
- ✅ 首次运行自动安装依赖
- ✅ 等待3秒确保服务启动
- ✅ 显示API地址和文档地址

### 方式2: 独立脚本
```bash
python start_backend.py
```

### 方式3: 手动启动
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

## 📊 访问系统

### 前端界面
启动前端后，访问：
- **主页**: http://localhost:5173
- **数据看板**: http://localhost:5173/dashboard
- **数据采集**: http://localhost:5173/collection
- **数据管理**: http://localhost:5173/management
- **账号管理**: http://localhost:5173/accounts
- **字段映射**: http://localhost:5173/field-mapping

### 后端API
启动后端后，访问：
- **API文档**: http://localhost:8000/api/docs
- **RedDoc文档**: http://localhost:8000/api/redoc
- **健康检查**: http://localhost:8000/health

## 🎮 完整使用流程

### 场景1: 日常数据管理

```
1. python run_new.py
2. 选择 "5" - 前端页面管理
3. 选择 "1" - 启动前端服务
4. 选择 "5" - 在浏览器中打开
5. 返回主菜单 "0"
6. 选择 "2" - 后端API管理
7. 选择 "1" - 启动后端服务
8. 开始使用系统

前端访问: http://localhost:5173
后端API: http://localhost:8000/api/docs
```

### 场景2: 数据采集任务

```
1. 启动系统（前端+后端）
2. 访问前端: http://localhost:5173
3. 点击"数据采集中心"
4. 启动全平台采集
5. 实时监控采集状态
6. 查看采集历史记录
```

### 场景3: 字段映射审核

```
1. 启动系统（前端+后端）
2. 访问前端: http://localhost:5173
3. 点击"智能字段映射审核"
4. 扫描采集文件
5. 选择文件并预览
6. 生成智能映射
7. 确认并入库
```

## 🔧 管理功能

### 查看服务状态
```
前端管理菜单 → 选择 "4" 查看运行状态
后端管理菜单 → 选择 "4" 查看运行状态

显示信息:
- 🔘 状态: 运行中/未运行
- 🔗 访问地址
- 📁 目录路径
- 🔌 端口号
- 🆔 进程ID
- 🔗 连接数
```

### 重启服务
```
如果服务出现问题:
1. 进入对应的管理模块
2. 选择 "3" - 重启服务
3. 系统会自动停止并重新启动
```

### 停止服务
```
退出系统前:
1. 进入对应的管理模块
2. 选择 "2" - 停止服务
3. 确认停止
4. 返回主菜单 "0"
5. 退出系统 "0"
```

## 🐛 常见问题

### Q1: npm未找到
**症状**: 启动前端时提示"npm未找到"

**解决**:
1. 确认Node.js已安装（包含npm）
2. 将npm添加到系统PATH
3. 重启终端
4. 模块会自动尝试多个npm路径

### Q2: 依赖安装失败
**症状**: 首次启动时依赖安装失败

**解决**:
```bash
# 前端依赖
cd frontend
npm install

# 后端依赖
cd backend
pip install -r requirements.txt
```

### Q3: 端口被占用
**症状**: 提示端口5173或8000被占用

**解决**:
- 模块会自动检测并尝试清理端口
- 或手动终止占用进程：
```bash
# Windows
netstat -ano | findstr :5173
taskkill /PID <PID> /F

# Linux/macOS
lsof -i :5173
kill -9 <PID>
```

### Q4: 服务启动失败
**症状**: 服务启动后立即停止

**解决**:
1. 查看错误信息
2. 检查日志文件
3. 验证依赖安装
4. 尝试手动启动查看详细错误

## 💡 使用技巧

### 同时运行前后端
```bash
# 推荐方式：使用两个终端窗口

# 终端1: 启动主入口管理前端
python run_new.py
# 选择 5 → 1 启动前端

# 终端2: 启动主入口管理后端
python run_new.py  
# 选择 2 → 1 启动后端
```

### 开发调试
```bash
# 前端开发
cd frontend
npm run dev
# 支持HMR热更新，修改即时生效

# 后端开发  
cd backend
uvicorn main:app --reload
# 支持自动重载，修改代码自动重启
```

### 查看日志
```bash
# 前端：在浏览器控制台查看
F12 → Console

# 后端：在终端查看输出
# 或查看日志文件: logs/backend.log
```

## 📞 获取帮助

- 📖 查看文档: [README.md](../README.md)
- 📝 快速开始: [QUICK_START.md](QUICK_START.md)
- 🚀 部署指南: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
- 🐛 问题反馈: https://github.com/xihong-erp/xihong-erp/issues

---

**祝你使用愉快！🎉**
