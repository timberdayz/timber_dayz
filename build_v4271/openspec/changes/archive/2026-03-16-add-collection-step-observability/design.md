# Design: 采集步骤可观测与组件契约统一

## Context

- 采集任务由 executor_v2 执行，内部有 _update_status(task_id, progress, message)，但后台任务未注入 status_callback，导致进度与步骤未落库；CollectionTaskLog 仅在任务创建/取消等节点写入，执行过程无步骤记录。用户无法在界面上看到「哪一步失败」。
- 各平台组件 run() 存在 async 与 sync 混用，adapter 统一 await component.run() 时 sync 实现会出错或阻塞事件循环。

## Goals / Non-Goals

- **Goals**：执行过程中写入步骤级日志（CollectionTaskLog）并更新任务进度（CollectionTask.current_step、progress）；前端任务详情展示步骤时间线；组件 run() 统一为 async。
- **Non-Goals**：不实现 API 采集或采集方式分流；不强制组件内每一子步骤都打点（先保证执行器层步骤完整）。

## Decisions

### 1. 步骤日志写入方式：回调注入 + 接口扩展

- **决策**：在 _execute_collection_task_background 中创建 executor 时传入 status_callback；**回调签名需支持结构化 details**：要么扩展为 status_callback(task_id, progress, message, current_domain=None, details=None)，details 为 { step_id, component, data_domain, success, duration_ms, error }；要么新增 step_callback(task_id, details_dict) 专用于步骤开始/结束。执行器在步骤开始处调用回调（details 含 step_id、component、data_domain）；步骤结束处再次调用（details 含 success、duration_ms、失败时 error），由回调方写入 CollectionTaskLog 并 update CollectionTask。回调内根据 task_id（UUID）查 CollectionTask 得主键 id，用该 id 写 CollectionTaskLog。
- **理由**：现有回调仅 (task_id, progress, message)，无法写出完整 details；扩展后前端步骤时间线可展示步骤名与失败原因。
- **替代**：执行器直接接收 session 或 TaskService 实例——增加执行器与后端的耦合，不采纳。

### 1b. 回调内写库的 session 策略

- **决策**：回调内写 CollectionTaskLog 与 update CollectionTask 时使用**独立 session**（每次写入新建 AsyncSessionLocal()，写完后 commit 并 close），不与后台任务持有的 db session 混用，避免在回调内 commit 导致与 _execute_collection_task_background 的 commit 冲突或 session 状态不一致。**执行器侧**：调用步骤回调时与现有 _update_status 一致，对回调做 try/except，仅打日志、不 re-raise，确保回调失败（如 DB 异常）不会中断采集任务。
- **理由**：后台任务在 async with AsyncSessionLocal() as db 内执行 executor，若回调也使用同一 db 并在回调内 commit，易产生重复提交或竞态；独立 session 每次写一次 commit，语义清晰。回调异常不中断执行，保证可观测性写入失败不影响主流程。
- **替代**：回调只把「待写入数据」放入队列，由后台任务在同一 session 内顺序消费并写入——可行但需引入队列与消费逻辑，本变更优先采用独立 session。

### 2. details 结构约定

- **决策**：CollectionTaskLog.details（JSON）约定包含：step_id（如 login、export_orders）、component（如 login、orders_export）、data_domain（如 orders）、success（bool）、duration_ms（可选）、error（失败时的字符串）。前端与检索可依赖这些字段展示步骤名与失败原因。
- **理由**：现有 details 已为 JSON，无需改表；统一结构后前端可稳定解析并展示时间线。

### 3. 执行器打点粒度与并行路径

- **决策**：在各「逻辑步骤」**成对**打点：登录开始、登录结束（成功/失败，失败时 level=error、details.error）；每个数据域导出开始、导出结束（成功/失败，失败时 level=error、details.error）；文件处理开始、文件处理结束。步骤结束时的回调需带 success、duration_ms、失败时 error。**顺序执行（execute）**在循环内成对打点；**并行执行（execute_parallel_domains）**在 _execute_single_domain_parallel 或每域任务边界成对打点（单域开始/单域结束），与顺序路径语义一致。两种路径均注入同一 status_callback/step_callback。组件内部的子步骤通过 ctx.step_callback 上报为可选，本变更不强制。
- **理由**：成对打点便于前端展示「步骤名 + 成功/失败 + 耗时」；并行路径在单域边界打点避免只打 batch 层而漏掉单域粒度。

### 4. 组件 run() 统一为 async

- **决策**：基类与所有平台实现将 run() 改为 async def，内部统一使用 async Playwright API（await page.*）。TikTok/Amazon 当前 sync 实现改为 async；Shopee 的 services_export、analytics_export、**metrics_selector**（若被 call_component 调用）与 Miaoshou 的 export 若为 sync 则改为 async。所有通过 python_component_adapter（含 call_component）调用的组件均需为 async，避免 await 非协程报错。
- **理由**：adapter 与 executor 已按 await component.run() 设计；统一 async 后无混用导致的运行时错误与阻塞，且与 data-collection 规格「异步 Python 组件」一致。

### 5. 任务开始/结束时间（started_at / completed_at）

- **决策**：若 CollectionTask 表当前无 started_at、completed_at 列，则通过 Alembic 迁移与 schema.py 新增这两列；router 在任务开始（status=running）时写 started_at，在任务终态（completed/failed/cancelled 等）时写 completed_at。**同步更新** backend 任务相关 API 的响应模型（如 TaskResponse、任务详情/列表所用 Pydantic 模型），声明 started_at、completed_at 字段，保证任务详情与列表接口返回开始/结束时间。若表中已有这两列但 schema 未声明，则补全 schema、迁移与响应模型并与 router 一致。
- **理由**：当前 router 已使用 task.started_at / task.completed_at，若 schema 与迁移未包含则存在运行时 AttributeError 风险；响应模型不声明则前端可能拿不到这两项，统一后任务详情可稳定展示时间范围。

## 与 add-hybrid-collection-api-playwright 的关系

- **add-hybrid-collection-api-playwright**：新增采集方式（API vs Playwright）、API 采集器、落盘与登记；不涉及步骤日志与任务详情 UI，不涉及现有组件 run() 契约。
- **本变更**：不新增 API 采集；仅提升现有 Playwright 链路的可观测性（步骤日志、进度持久化、任务详情时间线）与组件一致性（run 统一 async）。两者可独立开发与上线。
