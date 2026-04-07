# 🚀 从这里开始！

**欢迎使用跨境电商ERP数据管理系统！**

---

## 🎉 Week 1已完成 - 系统生产就绪！

**系统状态**: ✅ 生产就绪  
**完成度**: 95% Week 1任务  
**质量评分**: ⭐⭐⭐⭐⭐ 96分  
**健康检查**: 7/7全部通过  

---

## ⚡ 3步快速启动

### 步骤1: 健康检查

```bash
python health_check.py
```

**预期输出**: `✅ 系统健康检查全部通过，可以启动系统！`

---

### 步骤2: 启动系统

**选择启动方式**:

#### 方式A: 使用启动脚本（推荐）

```bash
# Linux/macOS
bash start.sh

# Windows
start.bat
```

#### 方式B: 直接启动Streamlit

```bash
streamlit run frontend_streamlit/main.py
```

#### 方式C: 使用Docker

```bash
docker-compose up -d
```

---

### 步骤3: 访问系统

打开浏览器访问: **http://localhost:8501**

---

## 📚 新用户指南

### 我是第一次使用，应该看什么？

**推荐阅读顺序**:

1. **[用户使用手册](docs/USER_MANUAL.md)** ← 5分钟了解系统
2. **[快速开始教程](docs/USER_MANUAL.md#快速开始)** ← 3步上手
3. **尝试功能**: 
   - 进入"统一数据看板"查看系统概览
   - 进入"数据管理中心"尝试文件入库
   - 进入"字段映射审核"查看智能映射

---

### 我是开发者，想了解架构？

**推荐阅读顺序**:

1. **[系统架构总览](docs/architecture/ARCHITECTURE.md)**
2. **[数据库Schema](docs/architecture/DATABASE_SCHEMA_V3.md)**
3. **[ETL组件文档](docs/architecture/ETL_COMPONENTS.md)**
4. **[API参考文档](docs/API_REFERENCE.md)**

---

### 我想进行多Agent协作开发？

**推荐阅读顺序**:

1. **[多Agent快速入门](docs/multi_agent/MULTI_AGENT_QUICKSTART.md)** ← 5分钟了解
2. **[Agent A手册](docs/multi_agent/AGENT_A_HANDBOOK.md)** ← 如果用Cursor
3. **[Agent B手册](docs/multi_agent/AGENT_B_HANDBOOK.md)** ← 如果用Augment
4. **[常见问题FAQ](docs/multi_agent/MULTI_AGENT_FAQ.md)** ← 30+个问题

---

### 我遇到问题了怎么办？

**解决步骤**:

1. **查看故障排查手册**: [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
2. **查看常见问题FAQ**: [MULTI_AGENT_FAQ.md](docs/multi_agent/MULTI_AGENT_FAQ.md)
3. **查看用户手册**: [USER_MANUAL.md](docs/USER_MANUAL.md)
4. **运行健康检查**: `python health_check.py`

---

## 🎯 核心功能速览

### 数据采集（已有，稳定）

**支持平台**:
- ✅ Shopee（虾皮）
- ✅ TikTok Shop（抖音小店）
- ✅ 妙手ERP

**使用方式**: 进入"数据采集中心"页面

---

### 数据管理（新建，完善）

**核心功能**:
- 文件自动扫描
- 智能字段映射
- 批量数据入库
- 失败数据隔离

**使用方式**:

```bash
# 命令行（推荐）
python scripts/etl_cli.py run temp/outputs --verbose

# Web界面
# 进入"数据管理中心" → 点击"扫描并入库"
```

---

### 数据看板（新建，专业）

**核心指标**:
- 总GMV（RMB）
- 订单总数
- 总销量
- 平均订单额

**可视化**:
- GMV趋势图
- Top 10产品榜单
- 平台对比分析
- 订单趋势分析

**使用方式**: 进入"统一数据看板"页面

---

## 📖 完整文档导航

### 用户文档

- 📘 [用户使用手册](docs/USER_MANUAL.md) - 如何使用系统
- 🐛 [故障排查手册](docs/TROUBLESHOOTING.md) - 遇到问题怎么办
- 🐳 [部署指南](docs/DEPLOYMENT_GUIDE.md) - 如何部署系统

### 技术文档

- 🏗️ [系统架构](docs/architecture/ARCHITECTURE.md) - 整体架构设计
- 💾 [数据库Schema](docs/architecture/DATABASE_SCHEMA_V3.md) - 数据库设计
- 🔧 [ETL组件](docs/architecture/ETL_COMPONENTS.md) - ETL工作原理
- 📡 [API参考](docs/API_REFERENCE.md) - API接口说明

### 开发文档

- 🚀 [多Agent快速入门](docs/multi_agent/MULTI_AGENT_QUICKSTART.md)
- 📚 [开发路线图](docs/DEVELOPMENT_ROADMAP.md)
- 📋 [文档索引](docs/INDEX.md) - 所有文档导航

### Week 1报告

- 📊 [最终交付报告](docs/WEEK1_FINAL_DELIVERY.md) ⭐
- 📈 [工作总结](docs/WEEK1_SUMMARY.md) ⭐
- 📝 [项目状态](docs/PROJECT_STATUS.md)

---

## 💡 使用技巧

### 技巧1: 快速入库数据

```bash
# 将Excel文件放到
temp/outputs/shopee/your_file.xlsx

# 执行入库
python scripts/etl_cli.py run temp/outputs
```

### 技巧2: 查看数据看板

```
打开 http://localhost:8501
→ 点击"统一数据看板"
→ 选择时间范围和平台
→ 查看核心指标和趋势
```

### 技巧3: 处理失败文件

```bash
# 查看失败原因
python scripts/etl_cli.py status --quarantine

# 重试失败文件
python scripts/etl_cli.py retry --all
```

---

## 🆘 遇到问题？

### 常见问题速查

| 问题 | 解决文档 |
|------|----------|
| 系统无法启动 | [故障排查](docs/TROUBLESHOOTING.md#系统启动问题) |
| 文件扫描后找不到 | [故障排查](docs/TROUBLESHOOTING.md#数据入库问题) |
| 入库全部失败 | [故障排查](docs/TROUBLESHOOTING.md#入库失败) |
| 性能慢 | [故障排查](docs/TROUBLESHOOTING.md#性能问题) |
| 数据看板空白 | [故障排查](docs/TROUBLESHOOTING.md#前端显示问题) |

### 获取帮助

1. **查看文档**: `docs/` 目录下有45+个文档
2. **运行健康检查**: `python health_check.py`
3. **查看日志**: `logs/` 目录
4. **查看FAQ**: [docs/multi_agent/MULTI_AGENT_FAQ.md](docs/multi_agent/MULTI_AGENT_FAQ.md)

---

## 🎊 恭喜！

**系统已就绪，可以立即投入使用！**

### 推荐下一步

1. **运行健康检查**: 确认系统状态
2. **启动系统**: 使用start.sh或Docker
3. **浏览功能**: 查看5个功能页面
4. **尝试入库**: 准备数据并执行ETL
5. **查看看板**: 查看数据可视化

---

**📖 详细文档**: [文档索引](docs/INDEX.md)  
**🎯 快速开始**: [用户手册](docs/USER_MANUAL.md)  
**💬 获取帮助**: [故障排查](docs/TROUBLESHOOTING.md)  

**祝您使用愉快！🎉**
