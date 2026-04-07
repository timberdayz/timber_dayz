# 🚀 快速访问 - 重要文档清单

## 🎯 用户必读文档

### 📖 新手入门
1. **[用户操作指南](USER_GUIDE.md)** - 🎯 **最重要**，系统操作完整指南
2. **[故障排除指南](guides/TROUBLESHOOTING.md)** - 遇到问题时必看
3. **[API参考文档](guides/API_REFERENCE.md)** - 开发集成时必读

### 🔧 系统操作
- **启动系统**: `python run_new.py` → 选择4 → 选择3
- **访问界面**: http://localhost:5173
- **操作流程**: 扫描文件 → 选择文件 → 智能映射 → 验证数据 → 数据入库

## 🏗️ 开发者必读文档

### 💻 开发规范
1. **[开发框架](DEVELOPMENT_FRAMEWORK.md)** - 🏗️ **最重要**，开发规范和架构
2. **[未来开发计划](FUTURE_DEVELOPMENT_PLAN.md)** - 开发路线图和任务
3. **[完整系统报告](COMPLETE_SYSTEM_REPORT.md)** - 系统功能和架构说明

### 🔧 开发环境
- **部署指南**: [guides/DEPLOYMENT_GUIDE.md](guides/DEPLOYMENT_GUIDE.md)
- **Node.js配置**: [guides/NODEJS_INSTALLATION_GUIDE.md](guides/NODEJS_INSTALLATION_GUIDE.md)
- **测试指南**: [development/TESTING_SUMMARY.md](development/TESTING_SUMMARY.md)

## 📊 项目管理文档

### 📋 项目状态
- **[完整系统报告](COMPLETE_SYSTEM_REPORT.md)** - 系统功能总览
- **[未来开发计划](FUTURE_DEVELOPMENT_PLAN.md)** - 开发计划和时间线
- **[文档清理报告](DOCUMENTATION_CLEANUP_REPORT.md)** - 文档管理现状

### 📈 进度报告
- [reports/WORK_SUMMARY_2025_01_16.md](reports/WORK_SUMMARY_2025_01_16.md) - 今日工作总结
- [reports/WEEK1_ACCEPTANCE_REPORT.md](reports/WEEK1_ACCEPTANCE_REPORT.md) - Week 1验收报告

## 🎯 外键配置重点

### 常用外键映射
```
店铺相关:
- shop_id → dim_shops.shop_id
- store_id → dim_shops.shop_id

产品相关:
- product_id → dim_products.product_id
- sku → dim_products.product_sku

订单相关:
- order_id → fact_orders.order_id
- order_number → fact_orders.order_id
```

## 🔧 常见操作

### 系统启动
```bash
# 启动主系统
python run_new.py

# 选择操作：
# 4. Vue字段映射审核
# 3. 启动完整系统
```

### 文件处理流程
1. **扫描文件** → 点击"扫描采集文件"按钮
2. **选择文件** → 选择平台、数据域和具体文件
3. **智能映射** → 点击"🤖 智能映射"生成字段映射
4. **验证数据** → 点击"🔍 验证数据"检查数据质量
5. **数据入库** → 点击"📥 数据入库"完成处理

### 数据入库后检查
1. **验证入库结果** → 查看统计数据和错误记录
2. **数据库验证** → 检查目标表和数据完整性
3. **业务验证** → 验证数据一致性和关联关系

## 📞 技术支持

### 遇到问题时的查找顺序
1. **[故障排除指南](guides/TROUBLESHOOTING.md)** - 常见问题解决方案
2. **[用户操作指南](USER_GUIDE.md)** - 详细操作步骤
3. **[API参考文档](guides/API_REFERENCE.md)** - 技术接口说明
4. **[开发框架](DEVELOPMENT_FRAMEWORK.md)** - 技术架构和规范

### 文档结构
```
docs/
├── USER_GUIDE.md                      # 🎯 用户核心指南
├── DEVELOPMENT_FRAMEWORK.md           # 🏗️ 开发规范
├── COMPLETE_SYSTEM_REPORT.md          # 📊 系统报告
├── FUTURE_DEVELOPMENT_PLAN.md         # 🚀 开发计划
├── guides/                            # 📖 操作指南
├── development/                       # 💻 开发文档
├── reports/                           # 📊 项目报告
└── archive/                           # 🗄️ 归档文档
```

---

**快速访问原则**: 
- 🎯 **用户优先**: USER_GUIDE.md 最重要
- 🏗️ **开发者优先**: DEVELOPMENT_FRAMEWORK.md 最重要
- 📊 **项目管理者**: COMPLETE_SYSTEM_REPORT.md 最重要

**记住**: 遇到任何问题，先查看对应的指南文档！
