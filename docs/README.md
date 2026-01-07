# 西虹 ERP 系统 - 文档中心

**版本**: v4.19.0  
**更新**: 2026-01-03  
**架构**: ✅ 100% SSOT + Contract-First  
**状态**: ✅ 文档已重新组织（architecture/guides/DEVELOPMENT_RULES/）  
**新增**: ✅ 执行器统一管理和资源优化（ExecutorManager）

---

## 📚 核心文档（必读）⭐⭐⭐

### 🎯 Agent 开发者

**首次接手**（按顺序阅读）:

1. **[AGENT_START_HERE.md](AGENT_START_HERE.md)** - Agent 快速上手指南 ⭐⭐⭐
2. **[architecture/V4_6_0_ARCHITECTURE_GUIDE.md](architecture/V4_6_0_ARCHITECTURE_GUIDE.md)** - v4.6.0 架构指南 ⭐⭐⭐
3. **[architecture/FINAL_ARCHITECTURE_STATUS.md](architecture/FINAL_ARCHITECTURE_STATUS.md)** - 架构最终状态 ⭐⭐⭐
4. **[CORE_DATA_FLOW.md](CORE_DATA_FLOW.md)** - 核心数据流程设计（A 类/B 类/C 类）⭐⭐⭐
5. **[SEMANTIC_LAYER_DESIGN.md](SEMANTIC_LAYER_DESIGN.md)** - 物化视图设计 ⭐⭐⭐

**开发规范**（受保护目录，禁止自动清理）:

- **[DEVELOPMENT_RULES/](DEVELOPMENT_RULES/)** - 详细开发规范（企业级标准）⭐⭐⭐
  - [DATABASE.md](DEVELOPMENT_RULES/DATABASE.md) - 数据库设计规范
  - [API_DESIGN.md](DEVELOPMENT_RULES/API_DESIGN.md) - API 设计规范
  - [SECURITY.md](DEVELOPMENT_RULES/SECURITY.md) - 安全规范
  - [TESTING.md](DEVELOPMENT_RULES/TESTING.md) - 测试策略
  - [CODE_QUALITY.md](DEVELOPMENT_RULES/CODE_QUALITY.md) - 代码质量保证
  - [UI_DESIGN.md](DEVELOPMENT_RULES/UI_DESIGN.md) - UI 设计规范
  - [ERROR_HANDLING_AND_LOGGING.md](DEVELOPMENT_RULES/ERROR_HANDLING_AND_LOGGING.md) - 错误处理和日志
  - [MONITORING_AND_OBSERVABILITY.md](DEVELOPMENT_RULES/MONITORING_AND_OBSERVABILITY.md) - 监控和可观测性
  - [DEPLOYMENT.md](DEVELOPMENT_RULES/DEPLOYMENT.md) - 部署和运维

**日常开发**:

- **验证工具**: `python scripts/verify_architecture_ssot.py`
- **测试工具**: `python scripts/test_field_mapping_automated.py`
- **架构规范**: `.cursorrules`（项目根目录）

### 👥 普通用户

**快速开始**:

1. **[guides/QUICK_START_ALL_FEATURES.md](guides/QUICK_START_ALL_FEATURES.md)** - 5 分钟上手
2. **[USER_QUICK_START_GUIDE.md](USER_QUICK_START_GUIDE.md)** - 详细操作手册

### 🏢 技术团队

**领域指南**:

- **[guides/V4_4_0_FINANCE_DOMAIN_GUIDE.md](guides/V4_4_0_FINANCE_DOMAIN_GUIDE.md)** - 财务功能完整指南
- **[guides/EXECUTOR_MANAGER_GUIDE.md](guides/EXECUTOR_MANAGER_GUIDE.md)** - ExecutorManager 使用指南（v4.19.0 新增）⭐⭐⭐
- **[deployment/RESOURCE_CONFIGURATION.md](deployment/RESOURCE_CONFIGURATION.md)** - 资源配置指南（v4.19.0 新增）⭐⭐⭐
- **[DATA_SOURCE_AND_FIELD_MAPPING_DESIGN.md](DATA_SOURCE_AND_FIELD_MAPPING_DESIGN.md)** - 数据来源和字段映射设计

---

## 🗂️ 文档分类

### architecture/ - 架构设计

- `SYSTEM_ARCHITECTURE.md` - 系统架构总览
- `MODERN_UI_DESIGN_SPEC.md` - 现代化 UI 设计规范
- `V4_6_0_ARCHITECTURE_GUIDE.md` - v4.6.0 架构指南（维度表设计）⭐
- `FINAL_ARCHITECTURE_STATUS.md` - 架构最终状态（2025-01-30 审计）⭐

### deployment/ - 部署指南

- `DEPLOYMENT_GUIDE.md` - 部署步骤
- `DOCKER_QUICK_START.md` - Docker 快速启动
- `PRODUCTION_DEPLOYMENT_GUIDE.md` - 生产环境部署
- `RESOURCE_CONFIGURATION.md` - 资源配置指南（v4.19.0 新增）⭐⭐⭐

### guides/ - 用户和领域指南

- `QUICK_START_ALL_FEATURES.md` - 5 分钟快速上手指南 ⭐
- `V4_4_0_FINANCE_DOMAIN_GUIDE.md` - 财务功能完整指南 ⭐
- `EXECUTOR_MANAGER_GUIDE.md` - ExecutorManager 使用指南（v4.19.0 新增）⭐⭐⭐
- `RESOURCE_MONITORING_GUIDE.md` - 系统资源监控指南（v4.19.0 新增）⭐⭐⭐
- `FIELD_MAPPING_USER_GUIDE.md` - 字段映射用户指南
- `USER_GUIDE.md` - 用户手册
- 其他平台采集指南（Shopee、TikTok 等）

### DEVELOPMENT_RULES/ - 开发规范（受保护）⭐⭐⭐

- `README.md` - 规范索引
- `DATABASE.md` - 数据库设计规范
- `API_DESIGN.md` - API 设计规范
- `SECURITY.md` - 安全规范
- `TESTING.md` - 测试策略
- `CODE_QUALITY.md` - 代码质量保证
- `UI_DESIGN.md` - UI 设计规范
- `ERROR_HANDLING_AND_LOGGING.md` - 错误处理和日志
- `MONITORING_AND_OBSERVABILITY.md` - 监控和可观测性
- `DEPLOYMENT.md` - 部署和运维

> ⚠️ **重要**: `DEVELOPMENT_RULES/` 目录受保护，禁止 Agent 自动清理或移动文件

### development/ - 开发文档

- `DEVELOPMENT_ROADMAP.md` - 开发路线图
- `DEVELOPMENT_FRAMEWORK.md` - 开发框架
- `FRONTEND_GUIDE.md` - 前端开发指南
- `BACKEND_DEVELOPMENT_READY.md` - 后端开发指南
- **`DEVELOPMENT_RULES/`** - ⭐ 详细开发规范（受保护目录）
  - `README.md` - 详细规范文档索引
  - `DATABASE_DESIGN.md` - 数据库设计详细规范（P0）
  - `ERROR_HANDLING_AND_LOGGING.md` - 错误处理和日志详细规范（P0）
  - `MONITORING_AND_OBSERVABILITY.md` - 监控和可观测性详细规范（P0）
  - `API_DESIGN.md` - API 设计详细规范（P1）
  - `SECURITY.md` - 安全规范详细文档（P1）
  - `CODE_QUALITY.md` - 代码质量保证详细规范（P1）
  - `TESTING.md` - 测试策略详细规范（P2）
  - `DEPLOYMENT.md` - 部署和运维详细规范（P2）
  - ⛔ **保护机制**: 此目录下的所有文件禁止自动清理

### field_mapping_v2/ - 字段映射专题

- `README.md` - 字段映射系统概览
- `FIELD_MAPPING_V2_CONTRACT.md` - API 契约
- `FIELD_MAPPING_V2_OPERATIONS.md` - 运维指南
- `FIELD_DICTIONARY_REFERENCE.md` - 字段辞典内容对照表
- `time_fields/` - 时间字段专题文档
  - `TIME_FIELDS_AUDIT_AND_TEMPLATE_FIX.md` - 时间字段审查和模板匹配修复
  - `FINAL_TIME_FIELDS_REVIEW.md` - 时间字段设计最终审查
  - `DATE_FORMAT_STANDARDIZATION.md` - 日期格式标准化
  - `TIME_RANGE_FIELD_WITH_GRANULARITY.md` - 时间范围字段和粒度处理

### v3_product_management/ - 产品管理专题

- `V3_PRODUCT_VISUAL_MANAGEMENT_PLAN.md` - v3.0 产品管理规划
- `COMPLETE_FINAL_DELIVERY_v2_3_v3_0.md` - v2.3+v3.0 交付报告

### guides/ - 操作指南

- 26 个详细操作指南（用户手册）

### archive/ - 历史归档

- `20250130/` - 2025-01-30 归档（39 个文档）
- `2025_01/` - 2025 年 1 月归档
- `2025_10_phase_reports/` - 10 月阶段报告
- 其他历史归档

---

## 🎯 按需查阅

### 我要开始开发？

→ [AGENT_START_HERE.md](AGENT_START_HERE.md)

### 我要了解架构？

→ [FINAL_ARCHITECTURE_STATUS.md](FINAL_ARCHITECTURE_STATUS.md)

### 我要使用系统？

→ [QUICK_START_ALL_FEATURES.md](QUICK_START_ALL_FEATURES.md)

### 我要部署系统？

→ [deployment/DEPLOYMENT_GUIDE.md](deployment/DEPLOYMENT_GUIDE.md)

### 我要了解财务功能？

→ [V4_4_0_FINANCE_DOMAIN_GUIDE.md](V4_4_0_FINANCE_DOMAIN_GUIDE.md)

### 我要查阅历史？

→ [archive/](archive/) 目录

---

## 📊 文档统计

| 类别           | 数量  | 说明                                      |
| -------------- | ----- | ----------------------------------------- |
| 根目录核心文档 | 7 个  | 精简后的必读文档                          |
| 架构设计文档   | 2 个  | architecture/                             |
| 部署指南       | 5 个  | deployment/                               |
| 开发文档       | 6 个  | development/                              |
| 专题文档       | 20+   | field_mapping_v2/, v3_product_management/ |
| 操作指南       | 26 个 | guides/                                   |
| 历史归档       | 100+  | archive/                                  |

---

## 🔧 文档维护

### 核心文档（永久保留）⭐⭐⭐

docs 根目录仅保留核心文档（约 30 个）：

**Agent 必读（12 个）**:

1. `README.md` - 本文档（文档索引）
2. `AGENT_START_HERE.md` - Agent 快速上手
3. `CORE_DATA_FLOW.md` - 核心数据流程设计（v4.11.1 新增）
4. `DATA_SOURCE_AND_FIELD_MAPPING_DESIGN.md` - 数据来源和字段映射设计
5. `FINAL_ARCHITECTURE_STATUS.md` - 架构最终状态
6. `SEMANTIC_LAYER_DESIGN.md` - 物化视图设计
7. `MATERIALIZED_VIEW_MANAGEMENT_BEST_PRACTICES.md` - 物化视图管理
8. `ERP_UI_DESIGN_STANDARDS.md` - UI 设计标准
9. `BACKEND_DATABASE_DESIGN_SUMMARY.md` - 数据库设计总结
10. `QUICK_START_ALL_FEATURES.md` - 快速启动
11. `V4_4_0_FINANCE_DOMAIN_GUIDE.md` - 财务指南
12. `V4_6_0_USER_GUIDE.md` - 字段映射指南

**版本报告（10 个）**: v4.11.1、v4.11.0、v4.10.1、v4.9.3 系列

**用户指南（7 个）**: 妙手导入、产品管理、数据准备等

**其他重要文档（5 个）**: 数据隔离区、物化视图 FAQ、产品图片管理等

### 文档归档规则

**归档时机**:

- 交付报告完成后（7 天内归档）
- 版本升级后（老版本文档归档）
- 文档更新后（旧版本归档）

**归档位置**:

- `docs/archive/YYYYMMDD/` - 按日期归档
- `docs/archive/YYYY_MM/` - 按月度归档

**禁止操作**:

- ❌ 在 docs 根目录堆积超过 30 个文档
- ❌ 创建重复内容的文档
- ❌ 保留过时的交付报告和修复报告
- ❌ 保留临时工作文档（应归档）

**清理规则**（v4.11.1）:

- ✅ 版本报告：仅保留最新 3 个版本
- ✅ 修复报告：完成后立即归档
- ✅ 临时文档：完成后立即归档
- ✅ 重复文档：保留最终版，归档其他版本

---

## 🤖 Agent 接手检查清单

### 首次接手

- [ ] 阅读 `AGENT_START_HERE.md`
- [ ] 阅读 `FINAL_ARCHITECTURE_STATUS.md`
- [ ] 阅读项目根目录 `.cursorrules`
- [ ] 运行 `python scripts/verify_architecture_ssot.py`
- [ ] 确认 Compliance Rate = 100%

### 每次开发前

- [ ] 确认修改位置是否为 SSOT
- [ ] 确认不会创建 Base 类或重复定义
- [ ] 确认了解架构分层

### 每次开发后

- [ ] 运行架构验证脚本
- [ ] 确认合规率 100%
- [ ] 更新相关文档
- [ ] 清理临时文件

---

## 📞 支持

**技术问题**:

- 查阅对应专题文档
- 运行诊断脚本
- 查看历史归档

**架构问题**:

- 阅读 `ARCHITECTURE_AUDIT_REPORT_20250130.md`
- 运行 `verify_architecture_ssot.py`
- 查看 `.cursorrules`

---

**文档中心更新**: 2025-11-13（v4.11.1 清理）  
**文档管理**: AI Agent Team  
**清理统计**: 从 148 个 MD 文件精简到 33 个核心文档（精简 78%）  
**归档位置**: `docs/archive/20251113_cleanup/`（115 个文档）  
**下次整理**: 根据开发进展持续清理

_本文档索引遵循企业级 ERP 标准_
