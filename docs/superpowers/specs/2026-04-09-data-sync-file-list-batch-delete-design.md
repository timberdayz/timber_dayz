# Data Sync File List Batch Delete Design

**Date:** 2026-04-09

## Goal

为文件列表页面增加“多选删除”能力，使其与现有单文件删除保持完全一致地删除注册记录、本地文件、伴生 `.meta.json`、staging / quarantine / fact 关联数据，并顺带补强该页治理按钮的边界、文案与权限保护。

## Key Decision

采用“后端统一批量删除接口 + 前端批量影响确认”的方案，而不是前端循环调用单文件删除接口。

批量删除由后端复用现有 `CatalogFileDeleteService` 单文件删除逻辑逐项执行，并汇总结果返回前端。前端只负责选择、展示影响摘要、发起删除和呈现批量结果，不自行决定删除哪些伴生数据。

## Why

当前单文件删除已经有明确且较完整的边界：
- 删除 `CatalogFile`
- 删除本地文件
- 删除伴生 `.meta.json`
- 删除 `DataQuarantine`
- 删除 staging 表中的同 `file_id` 数据
- 删除对应 `b_class.fact_*` 表中的同 `file_id` 数据

这个边界已经被后端服务和测试固定下来。如果前端自行逐个请求单删接口：
- 交互会很差，用户需要面对重复确认或碎片化失败提示
- 批量结果难汇总，无法提供“成功 / 失败 / 跳过”总览
- 失败恢复不稳定，后续难以加入跳过 `processing`、部分成功、影响汇总等规则

因此批量删除必须在后端形成独立能力，但其内部必须复用单文件删除服务，保证规则单一来源。

## Scope

In scope:
- 在文件列表页增加“删除选中”入口
- 增加批量删除影响汇总 API
- 增加批量删除执行 API
- 对 `processing` 文件做删除保护
- 批量删除完成后刷新列表、统计和选中状态
- 为删除相关接口补上认证依赖
- 为“批量重试失败 / 手动全部数据同步 / 清理数据库”补强文案与低成本设计问题
- 补充批量删除后端测试

Out of scope:
- 重写现有单文件删除服务
- 引入新的任务中心或异步批量治理框架
- 一次性重构整个文件列表页面
- 让“清理数据库”变成真正意义上的全库治理工具
- 跨分页持久化勾选的复杂交互

## Existing Constraints

- 前端必须保持 Vue 3 + Element Plus + Pinia + Vite
- 后端必须保持 FastAPI + SQLAlchemy async + Pydantic
- 现有删除逻辑以 `backend/services/catalog_file_delete_service.py` 为准
- 当前会话需要在独立 git worktree 中执行，避免影响其他并行会话
- 仓库要求走 skill-first / superpowers 工作流

## Current State

### File List Page

`frontend/src/views/DataSyncFiles.vue` 当前支持：
- 多选同步
- 当前列表同步全部
- 全局“手动全部数据同步”
- 当前列表失败项批量重试
- 单文件删除

当前批量操作卡片只提供：
- “同步选中”
- “取消选择”

因此用户在需要删除多个文件时只能逐行点击“删除”。

### Single Delete Flow

前端：
- `GET /data-sync/files/{file_id}/delete-impact`
- `DELETE /data-sync/files/{file_id}`

后端：
- `backend/routers/data_sync.py`
- `backend/services/catalog_file_delete_service.py`

现状优点：
- 删除边界明确
- 已有 impact 预览
- 已有服务层测试

现状缺口：
- 没有批量 impact 汇总
- 没有批量删除 API
- 删除相关接口目前没有显式认证依赖

### Governance Buttons

“手动全部数据同步”：
- 走 `/data-sync/batch-all`
- 语义是“全局所有 pending 且匹配模板的文件”

“同步全部”：
- 走 `/data-sync/batch-by-ids`
- 语义是“当前页面列表中所有文件”

“批量重试失败”：
- 当前不是独立 retry API
- 仅筛选 `files.value` 中的 `failed / partial_success`，再调用 `/data-sync/batch-by-ids`

“清理数据库”：
- 仅清 `b_class.fact_*`
- 重置 `CatalogFile.status in ('ingested', 'partial_success', 'processing', 'failed')` 为 `pending`
- 不删除 staging / quarantine / 本地文件

## Proposed Design

### 1. Batch Delete Uses Dedicated Backend Endpoints

新增两个端点：
- `POST /data-sync/files/batch-delete-impact`
- `DELETE /data-sync/files/batch`

请求体包含：
- `file_ids: number[]`

影响汇总返回：
- `requested_count`
- `found_count`
- `missing_count`
- `processing_count`
- `deletable_count`
- `ingested_like_count`
- `fact_rows`
- `staging_rows`
- `quarantine_rows`
- `local_file_exists_count`
- `meta_file_exists_count`
- `items[]`

执行结果返回：
- `requested_count`
- `deleted_count`
- `failed_count`
- `skipped_count`
- `items[]`
- `warnings[]`

其中 `items[]` 至少包含：
- `file_id`
- `file_name`
- `status`
- `outcome` (`deleted` / `skipped` / `failed`)
- `message`

### 2. Reuse The Single Delete Service, Not Duplicate Rules

批量删除服务不直接写 SQL 规则，而是逐项调用现有 `CatalogFileDeleteService.delete_catalog_file()`。

只在批量层新增两类能力：
- 汇总 impact
- 对不允许删除的文件做统一跳过，例如 `processing`

### 3. Use Per-Item Isolation Instead Of One Giant Transaction

批量删除不应把全部文件包进一个大事务。

推荐策略：
- 每个文件单独执行删除
- 一个文件失败，只记录为 `failed`
- 整批继续执行后续文件

### 4. Frontend Adds One Batch Delete Entry Only In Selection Mode

当 `selectedFiles.length > 0` 时，在当前批量操作卡片中新增：
- “删除选中”
- “取消选择”

交互顺序：
1. 用户勾选文件
2. 点击“删除选中”
3. 前端请求 batch-delete-impact
4. 弹出汇总确认
5. 用户确认后请求 batch delete
6. 展示删除结果摘要
7. 刷新列表与统计，清空勾选

### 5. Initial Selection Scope Stays Current-Page Only

本次不做跨分页持久勾选。

### 6. Governance Buttons Keep Existing Backend Semantics But Need Clarification

#### 手动全部数据同步

保留现有实现，但文案改为更准确的“同步全部待同步文件（有模板）”。

#### 当前列表同步全部

保留现有实现，但文案改为“同步当前列表”。

#### 批量重试失败

保留当前技术路径，但文案改为“重试当前列表失败项”。

#### 清理数据库

保留为低优先级治理按钮，但需要：
- 加显式认证
- 改文案为“清空已入库事实数据并重置文件状态”
- 在说明中明确“不删除本地文件 / staging / quarantine”

## Security And Permission Fix

本次任务应顺手修复以下设计漏洞：
- 删除影响查询接口增加 `current_user = Depends(get_current_user)`
- 单文件删除接口增加 `current_user = Depends(get_current_user)`
- 批量删除相关新接口增加 `current_user = Depends(get_current_user)`
- 清理数据库接口增加 `current_user = Depends(get_current_user)`

本次先做到“认证必需”。更细的角色权限可以作为后续增强项。

## Testing Strategy

后端：
- 补批量 impact 聚合测试
- 补批量删除成功 / 部分失败 / 跳过 `processing` 测试
- 补认证要求测试

前端：
- 最低限度验证：
  - 选中后出现“删除选中”
  - 删除成功后会刷新并清空选择
  - 治理按钮文案与真实语义一致

## Recommended Rollout Order

1. 补删除/清理接口认证
2. 增加批量删除后端 contract 与实现
3. 增加前端“删除选中”
4. 调整治理按钮文案
5. 跑目标测试并手工验证
