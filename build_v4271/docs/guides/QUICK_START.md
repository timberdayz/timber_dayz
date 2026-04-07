# ⚡ 西虹ERP系统快速启动指南

## ⚠️ 重要更新 - v4.0.0混合架构

**统一启动方式**（2025-10-21更新）：本文档已更新到最新的混合架构启动方式。

---

5分钟快速上手西虹ERP系统！

## 📋 前置要求

在开始之前，请确保已安装：

- ✅ **Node.js** (>= 16.0.0)
- ✅ **Python** (>= 3.9)
- ✅ **npm** (>= 8.0.0)

检查版本：
```bash
node --version
python --version
npm --version
```

## 🚀 快速启动（2步）

### 步骤1: 克隆并安装依赖

```bash
# 克隆项目
git clone https://github.com/xihong-erp/xihong-erp.git
cd xihong-erp

# 安装Python依赖
pip install -r requirements.txt
```

### 步骤2: 一键启动

**推荐方式（一键启动前后端）**：
```bash
python run.py
```

**其他启动方式**：
```bash
# 仅启动后端
python run.py --backend-only

# 仅启动前端
python run.py --frontend-only

# 不自动打开浏览器
python run.py --no-browser

# CLI命令行模式
python run_new.py
```

## 🎉 完成！

系统将自动：
1. 检查依赖
2. 启动后端服务（http://localhost:8000）
3. 启动前端服务（http://localhost:5173）
4. 自动打开浏览器

现在你可以：
- 访问 **前端界面**: http://localhost:5173
- 访问 **API文档**: http://localhost:8000/api/docs
- 访问 **健康检查**: http://localhost:8000/health

---

## 📚 功能快速导航

### 1. 数据看板
访问首页查看核心KPI指标和数据统计

### 2. 数据采集
- 支持平台：Shopee、TikTok、Amazon、妙手ERP
- 自动化定时采集
- 实时状态监控

### 3. 字段映射审核
直达链接：http://localhost:5173/#/field-mapping
- AI智能字段识别
- 人机协同审核
- 批量数据入库

### 4. 数据管理
- 数据质量检查
- 智能数据清理
- 批量数据操作

---

## ❌ 已弃用的启动方式

以下启动脚本已在v4.0.0中移除，请勿使用：

~~`python start_frontend.py`~~ - 已移除，使用 `python run.py`  
~~`python start_backend.py`~~ - 已移除，使用 `python run.py --backend-only`  
~~`python start_erp.py`~~ - 已移除，使用 `python run.py`

---

## 🔧 常见问题

### Q1: 启动失败怎么办？
```bash
# 检查Python依赖
pip install -r requirements.txt

# 检查Node.js和npm
node --version
npm --version
```

### Q2: 端口被占用
```bash
# Windows查看端口占用
netstat -ano | findstr :8000
netstat -ano | findstr :5173

# 终止占用进程
taskkill /PID <进程ID> /F
```

### Q3: npm依赖安装失败
```bash
cd frontend
npm install --force
```

### Q4: 如何停止服务？
在运行窗口按 `Ctrl+C` 即可停止所有服务

---

## 🚀 下一步

- 📖 查看 [系统架构文档](../HYBRID_ARCHITECTURE_PLAN.md)
- 📖 查看 [部署指南](DEPLOYMENT_GUIDE.md)
- 📖 查看 [系统清理报告](../SYSTEM_CLEANUP_REPORT_20251021.md)

---

**更新日期**: 2025-10-21  
**适用版本**: v4.0.0 混合架构
