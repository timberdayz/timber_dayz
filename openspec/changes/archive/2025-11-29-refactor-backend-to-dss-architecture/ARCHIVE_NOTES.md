# 归档说明：refactor-backend-to-dss-architecture

**归档日期**: 2025-11-29  
**归档原因**: 核心功能已完成，部分工作延后到新 changes

## 归档操作

- ✅ Change 目录已从 `openspec/changes/refactor-backend-to-dss-architecture/` 移动到 `openspec/changes/archive/2025-11-29-refactor-backend-to-dss-architecture/`
- ✅ 所有文件完整保留，包括：
  - `proposal.md`（408 行）
  - `design.md`（641 行）
  - `tasks.md`（973 行）
  - `FINAL_SUMMARY.md`（260 行）
  - 所有 specs 目录（7 个 capability specs）
  - 所有状态报告和文档（40+ 个文件）

## 后续工作

以下工作已移交给新的 OpenSpec changes：

1. **`configure-metabase-dashboard-questions`**
   - 创建并配置所有业务概览相关的 Metabase Question
   - 配置 Question ID 环境变量，消除 Dashboard 相关 400 错误

2. **`migrate-frontend-dashboard-to-metabase-api`**
   - 将前端 Dashboard 页面迁移到 Metabase Question API
   - 清理旧 Dashboard API 依赖

3. **HR 前端与 C 类定时计算**（后续 change）
   - HR 管理前端页面
   - Metabase Scheduled Questions 定时计算 C 类数据

## Specs 状态

本 change 包含以下 specs（位于 `specs/` 目录）：

- `backend-architecture` - 后端架构规范（ETL 聚焦）
- `bi-layer` - BI 层规范（Metabase 集成）
- `dashboard` - Dashboard 规范（前端集成）
- `data-sync` - 数据同步规范（简化流程）
- `database-design` - 数据库设计规范（B/A/C 类数据表）
- `frontend-api-contracts` - 前端 API 契约规范
- `hr-management` - HR 管理规范

**注意**: 这些 specs 的 deltas 已包含在 change 的 `specs/` 目录中。如需更新主 `openspec/specs/` 目录，请参考 OpenSpec 的归档规范手动合并。

## 相关文档

- **最终总结**: `FINAL_SUMMARY.md` - 详细说明本 change 的交付内容和后续工作
- **提案文档**: `proposal.md` - 架构转型的详细说明
- **设计文档**: `design.md` - 技术决策和架构设计
- **任务清单**: `tasks.md` - 详细实施任务和验收标准

