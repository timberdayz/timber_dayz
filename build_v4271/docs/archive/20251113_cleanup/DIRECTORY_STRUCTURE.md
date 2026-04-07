# 西虹ERP系统 - 目录结构说明

**版本**: v4.4.0  
**更新**: 2025-01-30  
**标准**: 企业级现代化ERP

---

## 📂 项目根目录

```
xihong_erp/
├── README.md                    ✅ 项目说明（必读）
├── CHANGELOG.md                 ✅ 更新日志
├── .cursorrules                 ✅ 架构规范（强制遵守）
├── run.py                       ✅ 统一启动脚本（推荐）
├── alembic.ini                  ✅ 数据库迁移配置
├── requirements.txt             ✅ Python依赖
├── package.json                 ✅ Node.js依赖
├── local_accounts.py            ⚠️  账号配置（不提交Git）
├── backend/                     → 后端API
├── frontend/                    → 前端UI
├── modules/                     → 业务模块
├── docs/                        → 文档中心
├── scripts/                     → 工具脚本
├── migrations/                  → Alembic迁移
├── data/                        → 数据文件
├── temp/                        → 临时文件
├── backups/                     → 归档文件
└── docker/                      → Docker配置
```

**规则**:
- ✅ **根目录只保留**: README + CHANGELOG + 配置文件
- ❌ **禁止在根目录**: 创建其他MD文档（应放docs/）
- ❌ **禁止在根目录**: 创建临时脚本（应放scripts/或temp/）

---

## 📚 docs/ 文档中心

```
docs/
├── README.md                                 ✅ 文档索引（必读）
├── AGENT_START_HERE.md                       ✅ Agent快速上手
├── FINAL_ARCHITECTURE_STATUS.md              ✅ 最终架构状态
├── ARCHITECTURE_AUDIT_REPORT_20250130.md     ✅ 架构审计报告
├── ARCHITECTURE_CLEANUP_COMPLETE.md          ✅ 清理完成报告
├── V4_4_0_FINANCE_DOMAIN_GUIDE.md            ✅ 财务域指南
├── QUICK_START_ALL_FEATURES.md               ✅ 快速开始
├── USER_QUICK_START_GUIDE.md                 ✅ 用户手册
├── TODAY_COMPLETE_SUMMARY.md                 ✅ 今日工作总结
├── DIRECTORY_STRUCTURE.md                    ✅ 本文档
│
├── architecture/                             → 架构设计（2个）
│   ├── SYSTEM_ARCHITECTURE.md
│   └── MODERN_UI_DESIGN_SPEC.md
│
├── deployment/                               → 部署指南（5个）
│   ├── DEPLOYMENT_GUIDE.md
│   ├── DOCKER_QUICK_START.md
│   └── ...
│
├── development/                              → 开发文档（6个）
│   ├── DEVELOPMENT_ROADMAP.md
│   ├── FRONTEND_GUIDE.md
│   └── ...
│
├── field_mapping_v2/                         → 字段映射专题（13个）
│   ├── README.md
│   ├── FIELD_MAPPING_V2_CONTRACT.md
│   └── ...
│
├── v3_product_management/                    → 产品管理专题（2个）
│
├── guides/                                   → 操作指南（26个）
│
└── archive/                                  → 历史归档
    ├── 20250130/                            → 今日归档（42个）
    ├── 2025_01/                             → 1月归档（42个）
    ├── 2025_10_phase_reports/               → 10月归档（18个）
    └── ...
```

**规则**:
- ✅ **根目录保留**: 8-10个核心文档
- ✅ **专题文档**: 按功能组织子目录
- ✅ **历史文档**: 归档到archive/YYYYMMDD/
- ❌ **禁止堆积**: 根目录不超过15个文件

---

## 🏗️ modules/ 模块目录

```
modules/
├── core/                        ⭐ 核心基础设施（SSOT）
│   ├── db/
│   │   ├── schema.py            ⭐⭐⭐ 唯一ORM定义（51张表，1500+行）
│   │   └── __init__.py          导出所有模型
│   ├── config.py                ConfigManager
│   ├── logger.py                ERPLogger
│   ├── secrets_manager.py       环境变量管理
│   └── exceptions.py            统一异常
│
├── apps/                        → 业务应用
│   ├── collection_center/      数据采集中心
│   ├── vue_field_mapping/       字段映射
│   └── ...
│
├── platforms/                   → 平台适配器
│   ├── shopee/
│   ├── tiktok/
│   ├── amazon/
│   └── miaoshou/
│
└── services/                    → 共享服务
    ├── catalog_scanner.py       文件扫描服务
    └── ...
```

**核心规则**:
- ⭐ **modules/core/db/schema.py** - 唯一ORM定义位置
- ❌ **绝对禁止**: 在core之外定义Base或模型
- ✅ **正确做法**: 从`modules.core.db`导入

---

## 🔧 backend/ 后端目录

```
backend/
├── main.py                      ✅ FastAPI应用入口
├── models/
│   ├── database.py              ✅ 引擎+Session（不定义模型）
│   └── users.py                 ✅ 用户权限（使用core.Base）
├── routers/                     → API路由（18个）
│   ├── field_mapping.py
│   ├── field_mapping_dictionary.py
│   ├── finance.py               ⭐ v4.4.0新增
│   ├── procurement.py           ⭐ v4.4.0新增
│   └── ...
├── services/                    → 业务服务（28个）
│   ├── field_mapping_dictionary_service.py  ⭐ 今天修复
│   ├── excel_parser.py          ⭐ 智能解析器
│   └── ...
└── utils/
    ├── config.py                Settings（后端配置）
    └── postgres_path.py         PostgreSQL PATH管理
```

**核心规则**:
- ✅ **models/database.py**: 只负责引擎+Session
- ❌ **禁止**: 在models/下定义新表
- ✅ **正确**: 从`modules.core.db`导入所有模型

---

## 🎨 frontend/ 前端目录

```
frontend/
├── src/
│   ├── views/                   → 页面组件（13个）
│   │   ├── FieldMappingEnhanced.vue
│   │   ├── FinanceManagement.vue  ⭐ v4.4.0新增
│   │   ├── ProductManagement.vue
│   │   └── ...
│   ├── components/              → 可复用组件
│   ├── stores/                  → Pinia状态管理
│   ├── api/                     → API客户端
│   └── router/                  → 路由配置
├── package.json                 ✅ 前端依赖
└── vite.config.js               ✅ 构建配置
```

---

## 🔨 scripts/ 工具脚本

```
scripts/
├── verify_architecture_ssot.py              ⭐ SSOT验证工具
├── test_field_mapping_automated.py          ⭐ 自动化测试
├── deploy_finance_v4_4_0_enterprise.py      ⭐ 财务部署
├── cleanup_docs_comprehensive.py            ⭐ 文档清理
├── seed_finance_dictionary.py               财务字段初始化
└── ... (58个脚本)
```

**分类**:
- 验证工具: `verify_*.py`
- 测试工具: `test_*.py`
- 部署工具: `deploy_*.py`
- 数据初始化: `seed_*.py`

---

## 💾 data/ 数据目录

```
data/
├── raw/                         → 原始采集数据（848个文件）
├── processed/                   → 已处理数据
├── input/                       → 手动上传
├── output/                      → 导出结果
├── product_images/              → 产品图片
├── archive/                     → 历史归档
├── quarantine/                  → 数据隔离区
└── unified_erp_system.db        ⚠️  SQLite备份（已迁移PostgreSQL）
```

---

## 📦 backups/ 归档目录

```
backups/
├── 20250130_architecture_cleanup/    ⭐ 今天归档（5个代码文件）
├── 20250124_architecture_cleanup/    之前的清理
├── legacy_20250809/                  遗留代码
└── ... (其他历史归档)
```

**规则**:
- ✅ 所有删除的文件先归档
- ✅ 按日期组织（YYYYMMDD_描述）
- ✅ 保留3-6个月
- ✅ 超过6个月可删除

---

## 🧪 temp/ 临时目录

```
temp/
├── development/                 → 开发调试脚本（7天清理）
├── outputs/                     → 输出结果（30天清理）
├── media/                       → 截图录屏（90天清理）
├── logs/                        → 日志文件（180天清理）
└── ... (2638个临时文件)
```

**自动清理策略**:
- 开发文件: 7天
- 输出文件: 30天
- 媒体文件: 90天
- 日志文件: 180天

---

## 🎯 核心文件定位

### 我要找ORM模型定义？
→ `modules/core/db/schema.py`（唯一位置）

### 我要找API路由？
→ `backend/routers/`目录

### 我要找业务逻辑？
→ `backend/services/`目录

### 我要找前端页面？
→ `frontend/src/views/`目录

### 我要找配置文件？
→ `config/`目录（YAML）或`.env.example`

### 我要找文档？
→ `docs/README.md`开始

---

## 📋 目录创建规则

### 允许创建（有明确规则）

- `temp/development/` - 临时开发脚本
- `backups/YYYYMMDD_描述/` - 归档目录
- `docs/archive/YYYYMMDD/` - 文档归档
- `data/input/项目名/` - 项目数据

### 禁止创建

- ❌ `legacy_*` - 使用backups归档
- ❌ `*_backup/` - 使用Git版本控制
- ❌ `test_*`（根目录）- 应在tests/或scripts/
- ❌ 随意的目录名 - 必须符合架构

---

## 🎓 目录设计原则

### 1. 单一职责
每个目录只负责一类文件

### 2. 清晰命名
目录名清晰表达用途

### 3. 分层组织
按功能/时间/类型分层

### 4. 易于查找
常用文件在浅层

### 5. 自动清理
临时文件定期清理

---

**最后更新**: 2025-01-30 01:05  
**维护**: AI Agent Team  
**状态**: ✅ 整洁有序

*本文档遵循企业级ERP组织标准*

