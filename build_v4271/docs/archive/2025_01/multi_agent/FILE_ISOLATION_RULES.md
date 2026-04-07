# 文件修改权限隔离规则

## 📋 文档说明

本文档明确定义Agent A和Agent B的文件修改权限，确保双方在串行开发时不会产生冲突。**修改任何文件前，请先查看此文档确认权限。**

## 🎯 核心原则

### 1. 严格隔离
- Agent A专注后端/数据库，Agent B专注前端/工具
- 禁止修改对方专属目录的文件
- 共享文件需要协调后再修改

### 2. 接口优先
- 修改共享文件前先定义接口契约
- 接口变更必须通知对方
- 保持接口向后兼容

### 3. 禁止修改冻结区域
- 数据采集模块（modules/apps/collection_center/）已冻结
- 采集前端页面（10_数据采集中心.py）已冻结
- 除非明确需求，否则不修改冻结区域

---

## 📊 完整权限矩阵

| 目录/文件路径 | Agent A | Agent B | 说明 |
|--------------|---------|---------|------|
| **数据库相关** ||||
| models/ | ✅ | ❌ | 数据库ORM模型 |
| models/dimensions.py | ✅ | ❌ | 维度表模型 |
| models/facts.py | ✅ | ❌ | 事实表模型 |
| models/management.py | ✅ | ❌ | 管理表模型 |
| models/database.py | ✅ | ❌ | 数据库连接管理 |
| migrations/ | ✅ | ❌ | Alembic迁移脚本 |
| migrations/versions/*.py | ✅ | ❌ | 迁移版本文件 |
| **服务层（Agent A专属）** ||||
| services/etl_pipeline.py | ✅ | ❌ | ETL主流程 |
| services/excel_parser.py | ✅ | ❌ | Excel解析器 |
| services/data_validator.py | ✅ | ❌ | 数据验证器 |
| services/data_importer.py | ✅ | ❌ | 数据入库引擎 |
| services/field_mapping/ | ✅ | ❌ | 字段映射模块 |
| services/field_mapping/scanner.py | ✅ | ❌ | 文件扫描器 |
| services/field_mapping/excel_reader.py | ✅ | ❌ | Excel读取器 |
| services/field_mapping/mapper.py | ✅ | ❌ | 字段映射引擎 |
| services/field_mapping/validator.py | ✅ | ❌ | 映射验证器 |
| **服务层（Agent B专属）** ||||
| services/data_query_service.py | 📋 | ✅ | 数据查询服务（需协调） |
| services/currency_service.py | ❌ | ✅ | 汇率服务 |
| **前端（Agent B专属）** ||||
| frontend_streamlit/pages/20_数据管理中心.py | ❌ | ✅ | 数据管理中心页面 |
| frontend_streamlit/pages/40_字段映射审核.py | ❌ | ✅ | 字段映射审核页面 |
| frontend_streamlit/unified_dashboard.py | ❌ | ✅ | 统一看板 |
| frontend_streamlit/components/ | ❌ | ✅ | UI组件 |
| frontend_streamlit/utils/ | ❌ | ✅ | 前端工具函数 |
| **工具类（Agent B专属）** ||||
| utils/file_tools.py | ❌ | ✅ | 文件工具 |
| utils/monitoring.py | ❌ | ✅ | 监控工具 |
| **测试** ||||
| tests/test_excel_parser.py | ✅ | ❌ | Excel解析器测试 |
| tests/test_field_mapper.py | ✅ | ❌ | 字段映射测试 |
| tests/test_etl_pipeline.py | ✅ | ❌ | ETL流程测试 |
| tests/test_frontend.py | ❌ | ✅ | 前端测试 |
| tests/test_currency_service.py | ❌ | ✅ | 汇率服务测试 |
| **配置文件（需协调）** ||||
| config/database.yaml | 📋 | 📋 | 数据库配置 |
| config/field_mappings.yaml | 📋 | ❌ | 字段映射配置 |
| **文档（共享）** ||||
| docs/API_CONTRACT.md | ✅ | ✅ | 接口契约（共同维护） |
| docs/DATABASE_SCHEMA_V3.md | ✅ | ❌ | 数据库设计 |
| docs/ETL_ARCHITECTURE.md | ✅ | ❌ | ETL架构 |
| docs/DEPLOYMENT_GUIDE.md | ✅ | ✅ | 部署指南 |
| docs/QUICK_START.md | ❌ | ✅ | 快速开始指南 |
| docs/USER_MANUAL.md | ❌ | ✅ | 用户手册 |
| docs/FRONTEND_PERFORMANCE.md | ❌ | ✅ | 前端性能文档 |
| **禁止修改区域（双方都不能改）** ||||
| modules/apps/collection_center/ | ❌ | ❌ | 数据采集模块（冻结） |
| frontend_streamlit/pages/10_数据采集中心.py | ❌ | ❌ | 采集前端（冻结） |
| local_accounts.py | ❌ | ❌ | 账号配置（不改） |
| .cursorrules | ❌ | ❌ | 开发规范（除非协商） |

**符号说明**:
- ✅ 可以自由修改
- ❌ 严格禁止修改
- 📋 需要协调后修改（先在docs/API_CONTRACT.md中定义接口）

---

## 🚨 特殊场景处理

### 场景1：需要修改共享文件
**例子**：Agent B需要修改`services/data_query_service.py`添加新查询方法

**正确流程**：
1. 在`docs/API_CONTRACT.md`中提出需求
2. 定义新方法的接口签名（参数、返回值、异常）
3. Agent A确认接口可行
4. Agent A实现接口
5. Agent B调用新接口

**错误做法**：
- ❌ 直接修改`services/data_query_service.py`
- ❌ 修改接口后不通知对方
- ❌ 不定义接口就开始实现

### 场景2：发现对方代码有bug
**例子**：Agent B发现`services/etl_pipeline.py`有bug

**正确流程**：
1. 记录bug详情（错误信息、复现步骤）
2. 在Git创建Issue或在文档中记录
3. 通知Agent A修复
4. 如果紧急，可以创建hotfix分支并标注

**错误做法**：
- ❌ 直接修改`services/etl_pipeline.py`
- ❌ 不通知对方就改了
- ❌ 不记录问题详情

### 场景3：需要添加新的共享工具类
**例子**：需要一个日期格式化工具，Agent A和B都要用

**正确流程**：
1. 在`docs/API_CONTRACT.md`中定义接口
2. 决定由谁实现（通常Agent B负责工具类）
3. 实现后放在`utils/`目录
4. 双方导入使用

**文件放置**：
- 如果是前端专用工具 → `frontend_streamlit/utils/`
- 如果是后端专用工具 → `services/`或`models/`
- 如果是共享工具 → `utils/`（Agent B负责）

### 场景4：需要临时调试对方的代码
**例子**：Agent B需要调试`services/etl_pipeline.py`找问题

**正确流程**：
1. 可以阅读代码，不修改
2. 可以添加print/log语句临时调试
3. 调试完成后**删除调试代码**
4. 如果需要永久修改，通知Agent A

**错误做法**：
- ❌ 修改核心逻辑
- ❌ 留下调试代码不清理
- ❌ 不通知对方就改了

---

## 📂 目录结构速查

### Agent A专属目录树
```
models/                       # ✅ 完全控制
├── __init__.py
├── base.py
├── dimensions.py             # 你创建的
├── facts.py                  # 你创建的
├── management.py             # 你创建的
└── database.py               # 你修改的

migrations/                   # ✅ 完全控制
├── env.py
└── versions/
    └── 001_initial_schema.py # 你创建的

services/                     # ✅ 部分控制
├── etl_pipeline.py           # 你创建的
├── excel_parser.py           # 你创建的
├── data_validator.py         # 你创建的
├── data_importer.py          # 你创建的
├── data_query_service.py     # 📋 需协调
├── currency_service.py       # ❌ Agent B的
└── field_mapping/            # ✅ 你的模块
    ├── __init__.py
    ├── scanner.py
    ├── excel_reader.py
    └── mapper.py

tests/                        # ✅ 部分控制
├── test_excel_parser.py      # 你创建的
├── test_field_mapper.py      # 你创建的
├── test_data_importer.py     # 你创建的
└── test_etl_pipeline.py      # 你创建的
```

### Agent B专属目录树
```
frontend_streamlit/           # ✅ 完全控制
├── pages/
│   ├── 10_数据采集中心.py    # ❌ 冻结（不能改）
│   ├── 20_数据管理中心.py    # 你修改的
│   ├── 40_字段映射审核.py    # 你修改的
│   └── unified_dashboard.py  # 你修改的
├── components/               # 你创建的组件
├── utils/                    # 你创建的工具
└── ...

services/                     # ✅ 部分控制
├── data_query_service.py     # 📋 需协调（主要由你调用）
└── currency_service.py       # 你创建的

utils/                        # ✅ 完全控制
├── file_tools.py             # 你创建的
└── monitoring.py             # 你创建的

tests/                        # ✅ 部分控制
├── test_frontend.py          # 你创建的
└── test_currency_service.py  # 你创建的
```

---

## 🔍 快速检查方法

### 修改前自检
**命令**：
```bash
# 检查文件是否在你的权限范围内
# 方法1：查看此文档的权限矩阵

# 方法2：查看文件路径
# Agent A: 如果路径包含 models/ 或 migrations/ 或 services/etl* → ✅
# Agent B: 如果路径包含 frontend_streamlit/ 或 utils/ → ✅
```

### 修改后检查
```bash
# 检查是否误改了对方的文件
git status

# 如果看到不属于你的目录，立即撤销
git checkout -- <误修改的文件>
```

---

## ⚠️ 违规处理

### 轻微违规（可以修复）
- 误改了对方的文件 → 立即撤销：`git checkout -- <file>`
- 忘记协调就改了共享文件 → 在docs/API_CONTRACT.md中补充说明

### 严重违规（需要重做）
- 修改了冻结区域 → 必须回滚到修改前的状态
- 破坏了对方的核心逻辑 → 联系对方协商解决

### 预防措施
- 每次修改前查看此文档
- 提交前检查git status
- 使用.cursorrules中的自检清单

---

## 📝 权限申请流程

如果你觉得某个文件的权限不合理，可以提出申请：

1. 在docs/中创建`PERMISSION_REQUEST.md`
2. 说明需要修改的文件和原因
3. 提出新的权限分配方案
4. 双方协商后更新此文档

---

## 🎯 最佳实践

### Do（应该做）
- ✅ 修改前查看权限矩阵
- ✅ 不确定时先查文档
- ✅ 共享文件先定义接口
- ✅ 发现对方bug及时通知
- ✅ 每天提交前检查git status

### Don't（不应该做）
- ❌ 不看文档就修改
- ❌ 改了不通知对方
- ❌ 修改冻结区域
- ❌ 破坏对方的接口
- ❌ 留下调试代码

---

## 📞 协调联系

### 需要协调的场景
1. 修改共享文件（services/data_query_service.py等）
2. 修改接口签名
3. 添加新的共享工具类
4. 发现对方代码有bug
5. 权限分配不合理

### 协调方式
- 更新`docs/API_CONTRACT.md`
- 在Git提交中注明"⚠️ 需要协调"
- 创建Issue或在文档中记录

---

**版本**: v1.0  
**创建日期**: 2025-10-16  
**最后更新**: 2025-10-16  
**维护者**: Agent A + Agent B  
**状态**: 强制执行中

