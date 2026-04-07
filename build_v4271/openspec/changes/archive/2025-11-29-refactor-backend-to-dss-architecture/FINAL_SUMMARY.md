# 最终总结：后端重构为 DSS 架构（refactor-backend-to-dss-architecture）

**Change ID**: `refactor-backend-to-dss-architecture`  
**创建时间**: 2025-01-31  
**完成时间**: 2025-11-29  
**状态**: ✅ 核心功能已完成，部分工作延后到新 changes

---

## 1. 变更概览（What was delivered）

### 1.1 架构转型

- **后端从「计算引擎 + 物化视图」转型为「ETL + DSS（Metabase）」**
  - 后端专注于数据采集、清洗、验证、入库（ETL 流程）
  - KPI 计算逻辑从 Python 硬编码迁移到 Metabase Question 声明式定义
  - 物化视图语义层已废弃，Metabase 直接查询 PostgreSQL 原始表

- **引入 B/A/C 三类数据模型**
  - **B 类数据**：业务数据（订单、产品、库存、流量等），存储在 `fact_raw_data_*` 表中（JSONB 格式，中文字段名）
  - **A 类数据**：用户配置数据（目标、成本、战役、员工等），存储在 `a_class` schema 中（中文字段名）
  - **C 类数据**：系统计算数据（绩效、提成等），存储在 `c_class` schema 中（中文字段名，由 Metabase 定时计算）

### 1.2 数据库结构重构

- **B 类数据分表**（按 `data_domain + granularity` 分表，最多 16 张表）
  - `fact_raw_data_orders_daily/weekly/monthly`（3 张）
  - `fact_raw_data_products_daily/weekly/monthly`（3 张）
  - `fact_raw_data_traffic_daily/weekly/monthly`（3 张）
  - `fact_raw_data_services_daily/weekly/monthly`（3 张）
  - `fact_raw_data_inventory_snapshot`（1 张）
  - 未来：`fact_raw_data_inventory_daily/weekly/monthly`（3 张）

- **统一对齐表**（`entity_aliases`，1 张）
  - 替代 `dim_shops` 和 `account_aliases` 两张表
  - 统一管理账号和店铺别名映射

- **A 类数据表**（7 张，使用中文字段名）
  - `sales_targets_a`、`sales_campaigns_a`、`operating_costs`
  - `employees`、`employee_targets`、`attendance_records`、`performance_config_a`

- **C 类数据表**（4 张，使用中文字段名）
  - `employee_performance`、`employee_commissions`、`shop_commissions`、`performance_scores_c`

- **数据库 Schema 分离**
  - `b_class`：B 类数据表
  - `a_class`：A 类数据表
  - `c_class`：C 类数据表
  - `core`：核心 ERP 表（catalog_files、field_mapping_dictionary 等）
  - `finance`：财务域表（如需要保留）

### 1.3 字段映射与数据同步重构

- **字段映射系统重构**
  - 从「标准字段映射」改为「原始中文表头 + JSONB」
  - 模板只保存 `platform + data_domain + granularity + header_columns`（原始表头字段列表）
  - 移除 `FieldMappingTemplateItem` 表（不再需要字段映射项表）
  - 实现表头变化检测和提醒功能

- **数据同步系统重构**
  - 支持用户手动选择表头行（解决自动检测效果不佳的问题）
  - 模板驱动同步：用户选择表头行 → 预览验证 → 保存模板 → 自动同步时严格执行模板表头行
  - 完全独立系统：新数据同步功能完全独立于字段映射审核系统
  - 新增「数据同步」二级菜单，包含文件列表、文件详情、任务管理、历史记录、模板管理页面

- **数据入库优化**
  - 实现多层数据去重策略（文件级、行内、跨文件、业务语义）
  - 实现合并单元格处理增强（关键列强制填充）
  - 实现数据对齐准确性保障（pandas 原生对齐 + 字典结构保证 + 入库前验证）
  - 性能优化：批量哈希计算、批量去重查询、批量插入（1000 行 < 0.2 秒）

### 1.4 基础 BI 集成

- **Metabase 部署和配置**
  - 部署 Metabase 容器（Docker Compose）
  - 配置 PostgreSQL 数据库连接
  - 同步 B/A/C 类数据表到 Metabase（支持多 schema 分组显示）

- **后端 Metabase 集成**
  - 创建 `MetabaseQuestionService` 服务，支持通过 Question ID 查询数据
  - 创建 Dashboard API 路由，通过 Metabase Question 查询提供业务概览数据
  - 实现 Question ID 环境变量配置机制

---

## 2. 已完成的关键任务（Key completed items）

### 2.1 表结构与迁移

- ✅ B 类数据分表创建（最多 16 张表，按 data_domain + granularity 分表）
- ✅ 统一对齐表创建（`entity_aliases` 表）
- ✅ A 类数据表创建（7 张表，使用中文字段名）
- ✅ C 类数据表创建（4 张表，使用中文字段名）
- ✅ 人力管理表创建（7 张表，使用中文字段名）
- ✅ 数据库 Schema 分离（a_class/b_class/c_class/core/finance）
- ✅ PostgreSQL search_path 配置（确保代码可以访问所有 schema）
- ✅ 数据浏览器多 schema 支持（修复 data_browser.py，支持查询多个 schema）

### 2.2 字段映射与入库

- ✅ FieldMappingTemplate 重构（添加 `header_columns` JSONB 字段）
- ✅ 模板匹配逻辑重构（基于 `platform + data_domain + granularity`）
- ✅ 表头变化检测和提醒功能实现
- ✅ 多层数据去重服务实现（文件级、行内、跨文件、业务语义）
- ✅ 合并单元格处理增强（关键列强制填充）
- ✅ 数据对齐准确性保障（数据验证服务）
- ✅ 性能测试通过（1000 行 < 0.2 秒，10000 行 < 2 秒）

### 2.3 数据同步重构

- ✅ 用户手动选择表头行功能实现
- ✅ 新数据同步系统开发（完全独立于字段映射审核系统）
- ✅ 菜单结构更新（新增「数据同步」二级菜单）
- ✅ 前端页面开发（文件列表、文件详情、任务管理、历史记录、模板管理）
- ✅ 后端 API 开发（文件预览 API、模板保存 API、数据同步服务重构）

### 2.4 基础 Metabase 集成

- ✅ Metabase 容器部署（Docker Compose）
- ✅ PostgreSQL 数据库连接配置
- ✅ 表同步脚本创建（自动化同步 B/A/C 类数据表）
- ✅ Metabase 多 schema 支持验证（a_class/b_class/c_class/core/finance）

### 2.5 清理工作

- ✅ 三层视图 SQL 文件归档（atomic_views.sql、aggregate_mvs.sql、wide_views.sql）
- ✅ 废弃 API 代码标记（dashboard_api.py、metrics.py、store_analytics.py 等）
- ✅ 物化视图相关任务归档（mv_refresh.py、c_class_calculation.py）
- ✅ 代码库清理完成（SSOT 检查 100% 合规）

> 详细过程与测试结果见本目录下的 `*_REPORT.md` / `*_SUMMARY.md` / `*_STATUS.md` 文件。

---

## 3. 延后到新 Changes 的工作（Deferred to next changes）

以下工作 **不再由本 change 承担**，将通过新的 OpenSpec change 单独推进：

### 3.1 Metabase Question 配置与 Dashboard 对齐

**→ 由 `configure-metabase-dashboard-questions` change 负责：**

- 创建并文档化业务概览、清仓排名等必备 Question（7 个核心 Question）
- 配置 Question ID 环境变量，消除 Dashboard 相关 400 错误
- 创建 Metabase Dashboard 配置指南文档

**当前状态**：后端 Dashboard API 已实现，但 Metabase 中尚未创建对应的 Question，导致大量 400 错误。

### 3.2 前端 Dashboard 迁移到 Metabase API

**→ 由 `migrate-frontend-dashboard-to-metabase-api` change 负责：**

- 将 `Dashboard.vue` 等核心页面完全迁移到 Metabase Question API
- 清理旧 Dashboard API 依赖，确保前端不再调用物化视图语义层
- 实现并验证 Metabase 宕机时的前端降级策略

**当前状态**：前端仍有大量页面依赖旧的 Dashboard API，尚未完全适配 DSS + Metabase 模式。

### 3.3 HR 前端与 C 类定时计算

**→ 由后续 `hr-*` 系列 changes 负责：**

- HR 管理前端页面（员工管理、提成管理等）
- Metabase Scheduled Questions 定时计算 C 类数据并写回 PostgreSQL
- C 类数据计算逻辑优化和性能调优

**当前状态**：HR 管理表结构已创建，API 已实现，但前端页面和定时计算逻辑尚未完成。

---

## 4. 风险与现状（Current limitations）

### 4.1 已知限制

- **Metabase Question 配置缺失**
  - 部分 Dashboard API 当前仍依赖未配置的 Metabase Question ID，会在 Question 未配置时返回 400
  - **缓解措施**：由 `configure-metabase-dashboard-questions` change 负责创建和配置所有必备 Question

- **前端 Dashboard 迁移未完成**
  - 部分前端看板仍调用旧 Dashboard API，尚未完全适配 DSS + Metabase 模式
  - **缓解措施**：由 `migrate-frontend-dashboard-to-metabase-api` change 负责逐步迁移前端页面

- **C 类数据定时计算未上线**
  - C 类数据表已设计，但实际定时计算与回写逻辑尚未上线
  - **缓解措施**：由后续 HR 相关 change 负责实现 Metabase Scheduled Questions

### 4.2 架构一致性

- ✅ **后端架构**：100% 符合 DSS 架构设计，所有 Dashboard API 通过 Metabase Question 查询
- ⏳ **前端架构**：部分页面已适配，部分页面仍使用旧 API（待迁移）
- ✅ **数据库架构**：100% 符合 DSS 架构设计，B/A/C 类数据表结构完整

> 以上限制已在新的 changes 中被显式建模，不再视为本 change 的未完成项。

---

## 5. 建议的下一步（Next steps）

### 5.1 立即执行（高优先级）

1. **配置 Metabase Dashboard Questions**
   - 按照 `configure-metabase-dashboard-questions` change 创建和配置所有必备 Question
   - 完成 Question ID 环境变量配置与验证
   - 消除 Dashboard 相关 400 错误

2. **迁移前端 Dashboard**
   - 按照 `migrate-frontend-dashboard-to-metabase-api` change 逐步迁移前端 Dashboard 与核心分析视图
   - 确保前后端架构完全统一

### 5.2 后续规划（中优先级）

3. **HR 前端与 C 类数据计算**
   - 创建独立的 HR 相关 change，完成 HR 管理前端页面
   - 实现 Metabase Scheduled Questions 定时计算 C 类数据

4. **性能优化与测试**
   - JSONB 查询性能优化（GIN 索引、查询优化）
   - 端到端测试（E2E）和性能测试
   - 降级策略完整测试

---

## 6. 相关文档（Related documents）

### 6.1 本 Change 相关文档

- **提案文档**：`proposal.md`（408 行，详细说明架构转型原因和变更内容）
- **设计文档**：`design.md`（641 行，详细技术决策和架构设计）
- **任务清单**：`tasks.md`（973 行，详细实施任务和验收标准）
- **状态报告**：`*_STATUS.md`、`*_SUMMARY.md`、`*_REPORT.md`（多个状态和总结文档）

### 6.2 相关 OpenSpec Changes

- **`configure-metabase-dashboard-questions`**：配置 Metabase Dashboard Questions
- **`migrate-frontend-dashboard-to-metabase-api`**：前端 Dashboard 迁移到 Metabase API

### 6.3 相关项目文档

- **架构指南**：`docs/AGENT_START_HERE.md`（Agent 快速上手指南）
- **DSS 架构提案**：`openspec/changes/refactor-backend-to-dss-architecture/proposal.md`

---

## 7. 总结（Conclusion）

本 change 成功完成了 DSS 架构重构的核心工作：

- ✅ **数据库层面**：B/A/C 类数据表结构完整，Schema 分离清晰
- ✅ **后端层面**：ETL 流程完整，Metabase 集成基础完成
- ✅ **数据同步**：新系统独立运行，用户体验提升
- ⏳ **前端层面**：部分页面已适配，部分页面待迁移（由新 change 负责）
- ⏳ **Metabase 配置**：Question 创建和配置待完成（由新 change 负责）

**本 change 的核心价值**：为系统从「数据采集工具」转型为「企业级 ERP 决策支持系统」奠定了坚实的架构基础。

---

_本文件用于帮助后续维护者快速理解 `refactor-backend-to-dss-architecture` 的交付边界，并将后续工作清晰移交给新的 OpenSpec changes。_

