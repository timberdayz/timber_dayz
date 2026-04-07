# ⚡ 新对话快速启动卡片

> **当前版本**: v4.0.0 | **状态**: ✅ 开发完成 | **下一步**: 优化和Bug修复

---

## 🎯 1分钟状态了解

**项目**: 西虹ERP系统（跨境电商智能管理平台）  
**完成度**: Phase 0-7 全部完成（100%）  
**代码量**: 118+文件，28,000+行代码  
**功能**: 52个核心功能全部实现  

---

## 📚 AI必读（5分钟）

### 必读优先级

**1️⃣ 开发规范** (1分钟):
```
.cursorrules
```
→ 了解所有开发约束和规范

**2️⃣ 新对话指南** (2分钟):
```
docs/NEXT_SESSION_START_HERE.md
```
→ 了解系统状态和工作重点

**3️⃣ 开发总结** (2分钟):
```
docs/FINAL_DEVELOPMENT_SUMMARY.md
```
→ 了解完整开发成果

---

## 🎯 下一步工作

### 优化和修复（当前阶段）

**优先级1: Bug修复**
- 修复审计服务数据库会话管理
- 完善API实现
- 修复性能监控依赖

**优先级2: 功能完善**
- 实现搜索功能
- 完善错误处理
- 优化加载状态

**优先级3: 性能优化**
- 数据库查询优化
- API响应优化
- 前端性能优化

---

## 🔍 快速定位

### 核心文件
```
run.py                    # 统一启动
backend/main.py           # 后端入口
frontend/src/main.js      # 前端入口
```

### API路由
```
backend/routers/
├── auth.py              # 认证（5端点）
├── users.py             # 用户（6端点）
├── roles.py             # 角色（5端点）
├── dashboard.py         # 看板（4端点）
└── performance.py       # 监控（10端点）
```

### 前端页面
```
frontend/src/views/
├── UserManagement.vue
├── RoleManagement.vue
├── PermissionManagement.vue
└── SalesDashboard.vue
```

---

## ⚠️ 关键约束

### 禁止操作
- ❌ 不要重构已完成架构
- ❌ 不要创建新的大型功能
- ❌ 不要修改核心业务逻辑（除非修复bug）
- ❌ 不要在根目录创建文档

### 必须遵守
- ✅ 遵循 `.cursorrules` 所有规范
- ✅ 修改前后都要测试
- ✅ 临时文件放入 `temp/`
- ✅ 文档放入 `docs/`

---

## 🚀 启动系统

```bash
# 后端
python run.py

# 前端（新终端）
cd frontend
npm run dev

# 访问
# 前端: http://localhost:3000
# API: http://localhost:8000/api/docs
```

---

## 📞 需要帮助？

查看完整文档:
- 📖 `docs/NEXT_SESSION_START_HERE.md` - 详细准备指南
- 📖 `docs/USER_MANUAL.md` - 用户手册
- 📖 `docs/PRODUCTION_DEPLOYMENT_GUIDE.md` - 部署指南

---

**开始工作吧！** 🚀🔧🐛
