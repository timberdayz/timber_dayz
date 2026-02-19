# Change: 数据采集模块前端整体修改

## Why

1. **前后端长期未对齐**：采集后端（执行器、任务状态、步骤日志、API 接口）已多次迭代，前端页面长时间未维护，出现接口/字段不一致、进度展示不全或错误（如进度始终 0%、状态与后端不符）等问题。
2. **可观测与操作入口不完整**：需要在前端完整支持「任务详情 + 步骤时间线」、手动采集与自动定时采集的配置与观测，避免遗漏或分散在多处修改。
3. **单独提案便于跟踪**：将数据采集模块前端的整体修改作为独立提案，与后端变更（如 add-collection-step-observability、add-hybrid-collection-api-playwright）分离，便于排期、验收和避免遗漏。

## What Changes

### 1. 菜单与路由

- 左侧菜单（数据采集与管理）与当前后端模块、权限一致；路由与后端 API 前缀一致。
- 确保「采集配置」「采集任务」「采集历史」等入口清晰可访问，与 `frontend/src/config/menuGroups.js`、`frontend/src/router/index.js` 及权限配置对齐。

### 2. 快速采集与任务列表（采集任务页）

- **快速采集表单**：平台、账号、数据域、日期范围、调试模式等字段与后端 `POST /collection/tasks` 入参一致；提交后任务出现在列表，错误提示与后端校验/错误码一致。
- **采集任务列表**：任务 ID、平台、账号、数据域、进度、当前步骤/数据域、状态、文件数、创建时间等与后端返回一致；筛选（全部/运行中/排队中/已完成/失败）与后端 query 一致。
- **操作**：取消、继续（暂停后）、重试（失败后）、「日志」按钮可用；「任务详情」入口（行点击或「查看详情」按钮）打开详情页或抽屉。

### 3. 任务详情与步骤时间线

- **任务详情**：展示任务元信息（平台、账号、状态、创建/开始/结束时间、总耗时、error_message、completed_domains、failed_domains 等），与后端 `GET /collection/tasks/:taskId` 及任务列表接口返回一致。
- **步骤时间线**：基于 `GET /collection/tasks/:taskId/logs`（或等价接口）返回的日志，按 timestamp 排序；若日志含 details（step_id、component、data_domain、success、duration_ms、error），按步骤展示；失败步骤高亮，details.error 可展开。
- **与「查看日志」**：保留现有「日志」弹窗（原始日志流），与「任务详情」中的步骤时间线互补。

### 4. 采集配置与定时

- **采集配置**：配置列表的 CRUD、筛选与后端一致；每条配置的「执行」按钮调用创建任务接口，创建后的任务在「采集任务」列表可见且状态正确。
- **定时配置**：启用定时、执行时间（cron 或预设）与后端调度接口一致；定时触发的任务在「采集任务」列表中展示，状态与后端一致。

### 5. 采集历史

- 历史列表、筛选、分页与后端 `GET /collection/history` 一致；详情（含成功域/失败域、错误信息）与后端一致；重试与后端 `POST /collection/tasks/:taskId/retry` 一致。
- 若与「采集任务」共用任务详情组件，历史详情中也可展示步骤时间线（通过同一 getTaskLogs 或任务日志接口）。

### 6. 实时进度与错误处理

- **WebSocket 或轮询**：若后端提供任务进度 WebSocket，前端消息结构与后端一致，用于刷新列表中的 progress、current_step、status；否则用轮询任务状态/任务详情接口，频率与后端负载可接受。
- **错误与空态**：接口错误时提示与后端错误码/文案一致；列表/详情空态、加载态明确，不出现字段缺失或 undefined 展示。

## Impact

### 受影响的规格

- **data-collection**：MODIFIED 增加前端需求（采集任务页、任务详情与步骤时间线、采集配置与定时、采集历史、与后端 API 契约一致）。

### 受影响的代码与文档

| 类型 | 位置/模块 | 修改内容 |
|------|-----------|----------|
| 前端 | frontend/src/views/collection/ | CollectionTasks.vue、CollectionConfig.vue、CollectionHistory.vue：表单字段、列表列、筛选、操作、任务详情与步骤时间线 |
| 前端 | frontend/src/api/collection.js | 与后端 API 路径、请求/响应字段对齐，必要时新增 getTaskLogs 的 details 解析说明 |
| 前端 | frontend/src/config/menuGroups.js、frontend/src/router/index.js | 菜单项与路由与采集模块一致；权限与 rolePermissions 一致 |
| 文档 | 数据采集相关使用/开发文档 | 补充前端入口说明：手动采集、自动定时、任务详情与步骤时间线查看方式 |

### 不修改

- 不在此变更中实现或修改后端采集执行器、组件、步骤日志写入逻辑（属 add-collection-step-observability 等后端提案）。
- 不修改非采集模块的前端页面（如数据同步、字段映射等），除非仅涉及菜单/路由命名对齐。

### 依赖关系

- **建议先完成**：add-collection-step-observability（步骤级日志与进度持久化、任务日志接口返回带 details 的结构），以便前端「任务详情 + 步骤时间线」有稳定数据源。
- **可选**：add-hybrid-collection-api-playwright 若落地，前端可在此提案或后续小改动中对接「采集方式」相关展示（如任务或配置中显示 api/playwright），本提案不强制依赖。

## Non-Goals

- 不在此变更中实现新的后端采集逻辑或 API 采集器。
- 不强制要求 UI 视觉大改版；以功能对齐、可观测与手动/自动流程可用为主。
- 组件录制、组件版本管理等其他采集相关子功能的前端改动不在本提案范围内，除非与采集任务/配置/历史共用同一列表或路由需一并调整。
