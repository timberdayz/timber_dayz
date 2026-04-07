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

### 5. 账号数据源（新采集系统统一）

- **唯一数据源**：数据库（`PlatformAccount` 表 / `account_loader_service`）。`GET /collection/accounts` 与 `POST /collection/tasks` 的账号校验、执行时加载的账号均由此获取，与「账号管理」一致。
- **不再使用**：`local_accounts.py`（LOCAL_ACCOUNTS）为旧采集系统使用方式，新采集 API 与前端不再依赖。
- **前端约定**：采集配置、采集任务页的账号下拉仅调用 `GET /collection/accounts`，创建任务时传递的 `account_id` 必须为该接口返回的 id，后端仅接受数据库中存在且启用的账号。

### 6. 快速采集扩展（数据域、日期、操作、调试说明）

- **数据域**：后端与 component_loader 支持 `orders, products, services, analytics, finance, inventory`。快速采集表单扩展为至少包含上述六项（或按平台动态展示），与后端一致，便于采集库存、财务、服务等。
- **日期范围**：在「今天」「昨天」「最近 7 天」基础上增加「最近 30 天」；并增加「自定义」选项，展示开始/结束日期选择器，提交时传 `date_range: { type: 'custom', start_date, end_date }` 或等价结构。
- **取消**：对状态为 pending / queued / running 的任务均展示「取消」按钮，调用现有取消 API；后端已支持取消 pending。
- **删除**：对终态任务（completed / failed / cancelled / partial_success）展示「删除」按钮，调用新增 `DELETE /api/collection/tasks/:taskId`；仅后端允许删除终态任务，物理删除记录。
- **调试模式说明**：在调试模式开关旁增加 tooltip 或文案：有头浏览器会在运行后端的电脑上打开；若任务一直处于「等待」请确认任务是否已开始执行（如后端单进程或任务队列是否正常）。
