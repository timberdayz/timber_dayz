# Design: 数据采集模块前端整体修改

## Context

- 采集后端已有任务模型、步骤日志（add-collection-step-observability 落地后）、配置与定时、历史与重试等接口；前端页面长期未同步，存在字段不一致、进度展示错误、缺少任务详情与步骤时间线等问题。
- 本变更仅涉及前端与对接契约，不实现新后端逻辑。

## Goals

- 菜单与路由与当前后端模块、权限一致。
- 快速采集、任务列表、任务详情与步骤时间线、采集配置与定时、采集历史与后端 API 完全对齐，支持手动与自动采集的完整观测与操作。
- 错误提示、加载态、空态明确，不出现未定义或错误字段展示。

## Decisions

### 1. 任务详情与步骤时间线数据源

- **任务元信息**：来自 `GET /collection/tasks/:taskId` 或列表行数据（若列表接口已返回足够字段）。
- **步骤时间线**：来自 `GET /collection/tasks/:taskId/logs`；日志条目的 `details`（JSON）约定含 step_id、component、data_domain、success、duration_ms、error，前端按 timestamp 排序后展示，失败步骤高亮并可展开 details.error。
- 与 add-collection-step-observability 的约定一致：执行器写入的 CollectionTaskLog 带 details，本变更仅消费并展示。

### 2. 实时进度更新方式

- **优先**：若后端提供 WebSocket（如 `/api/collection/ws/collection/:taskId`），前端连接后根据 message 更新列表行 progress、current_step、status、files_collected。
- **降级**：若无 WebSocket 或连接失败，对「运行中」「排队中」任务进行轮询（如每 5–10 秒请求任务列表或单任务详情），直至状态变为终态。

### 3. 页面范围

- **本提案范围内**：`frontend/src/views/collection/` 下的采集任务、采集配置、采集历史页面；`frontend/src/api/collection.js` 的请求/响应字段与后端一致；菜单与路由配置。
- **不在此范围**：组件录制、组件版本管理、数据同步、字段映射等页面的功能改动；仅当菜单/路由命名需与后端统一时做最小改动。

### 4. 与后端提案的衔接

- **add-collection-step-observability**：提供步骤级日志与进度持久化、任务日志接口带 details；本变更依赖该能力以展示步骤时间线，建议先完成或并行时约定接口契约。
- **add-hybrid-collection-api-playwright**：若落地，任务或配置可能新增「采集方式」等字段；本变更可预留展示位或在此提案验收后以小改动补充，不强制依赖。
