# Change: 采集步骤可观测与组件契约统一

## Why

1. **排错无界面**：采集脚本在 Cursor 中编写与修改，但任务运行时「哪一步失败、错误详情」无法在管理界面查看；仅能依赖最终 task.error_message 或服务器日志，运维与开发排错成本高。
2. **步骤不可见**：执行器有 status_callback 与 _update_status，但后台任务创建 executor 时未传入回调，进度与当前步骤未持久化到 DB；CollectionTaskLog 仅在任务创建/取消/重试时写入，执行过程中的「登录」「导出 orders」「导出 products」等步骤无记录。
3. **组件契约不一致**：各平台 Login/Export 的 run() 存在 async 与 sync 混用（如 TikTok/Amazon 为 sync、Shopee/Miaoshou 部分 async），adapter 统一 await component.run() 时 sync 组件会报错或阻塞；需统一为 async 并统一使用 async Playwright API，便于维护与可观测打点。

## What Changes

### 1. 执行过程中写入步骤级日志并持久化进度

- **回调接口扩展**：当前 status_callback 仅传 (task_id, progress, message, current_domain)，无法写出完整 details。需扩展为支持「步骤级」上报：要么扩展为 status_callback(task_id, progress, message, current_domain, details=None)，details 为 { step_id, component, data_domain, success, duration_ms, error }；要么在保留现有回调基础上增加 step_callback(task_id, details_dict)，供执行器在步骤开始/结束时调用。回调内根据 task_id（UUID）查询 CollectionTask 取主键 id，写入 CollectionTaskLog（level=info/error，message，details）并 update CollectionTask 的 current_step、progress。
- **步骤级日志**：在执行器**成对打点**——登录开始、登录结束（成功/失败）、每个数据域导出开始、导出结束（成功/失败）、文件处理开始、文件处理结束；失败时写入 level=error 及 details.error。顺序执行（execute）与**并行执行（execute_parallel_domains）**均注入同一回调，并在等价逻辑步骤处打点，保证两种模式都可观测。
- **进度持久化**：回调内更新 CollectionTask 的 current_step、progress；使用**独立 session**（每次写时新建 AsyncSession 或由后台任务在同一 session 内顺序写入、避免在回调内 commit 与外部冲突）写入 CollectionTaskLog 并 update CollectionTask。
- **任务时间字段**：若表结构尚无 started_at/completed_at，则通过迁移与 schema 为 CollectionTask 增加这两列，并在任务开始/完成时更新，供任务详情展示「开始/结束时间」；若已存在则仅确保 router 与 schema 一致。

### 2. 前端：任务详情与步骤时间线

- **任务详情**：在采集任务列表侧增加「任务详情」入口（如点击行或「查看详情」）；详情页或抽屉展示任务元信息（平台、账号、状态、时间、总耗时、error_message）及**按时间排序的步骤时间线**（基于 CollectionTaskLog 过滤该 task_id，按 timestamp 排序；若 details 含 step_id/component，可分组或标出步骤名）。
- **步骤展示**：每条日志展示时间、步骤名（或 step_id）、message、成功/失败；details 中的 error 可展开显示；可选展示 duration_ms。失败任务可高亮失败步骤。
- **与现有「查看日志」**：保留现有 getTaskLogs 的「查看日志」弹窗作为原始日志流；步骤时间线可作为「任务详情」中的结构化视图，二者互补。

### 3. 组件契约统一（run 为 async）

- **基类**：LoginComponent、ExportComponent、NavigationComponent、DatePickerComponent 的 run() 在基类中声明为 async def run(...)，并 raise NotImplementedError；文档注明所有实现必须为 async。
- **各平台实现**：将 TikTok/Amazon 的 sync run() 改为 async def run()，内部使用 async Playwright API（await page.goto 等）；Shopee 的 services_export、analytics_export、metrics_selector 与 Miaoshou 的 export 若当前为 sync，改为 async；所有通过 adapter 或 call_component 调用的组件均需为 async，避免 await 非协程报错。
- **不在此变更中**：不新增 API 采集器、不修改采集方式分流逻辑（属 add-hybrid-collection-api-playwright）。

### 4. 可选：组件内 report_step 与 step_callback 贯通

- 组件内关键子步骤（如「点击导出」「等待下载」）通过 ctx.step_callback 或 report_step 上报，执行器在「组件 run 前后」各打一条日志（如 step_id=platform.login.start / platform.login.end），便于时间线更细粒度；若当前 step_callback 未注入到 ctx，本变更至少保证执行器层的步骤日志完整，组件内打点为可选增强。

## Impact

### 受影响的规格

- **data-collection**：ADDED 采集任务步骤可观测（步骤级日志、进度持久化、任务详情步骤时间线）；MODIFIED 组件 run() 统一为 async。

### 受影响的代码与文档

| 类型     | 位置/模块                                      | 修改内容 |
|----------|-------------------------------------------------|----------|
| 后端     | backend/routers/collection.py（_execute_collection_task_background） | 创建 executor 时传入 status_callback；回调内写 CollectionTaskLog、更新 CollectionTask |
| 后端     | backend/services/task_service.py 或新建 step_log 服务 | 提供「按 task_id 写步骤日志、更新进度」的接口供回调使用（若不在 router 内直接写 DB） |
| 执行器   | modules/apps/collection_center/executor_v2.py   | 扩展回调调用处：在登录开始/结束、各数据域导出开始/结束、文件处理开始/结束成对打点，并传入 details（step_id、success、duration_ms、error）；顺序 execute 与并行 execute_parallel_domains 均注入同一回调 |
| 组件基类 | modules/components/login/base.py、export/base.py、navigation/base.py、date_picker/base.py | run() 改为 async def，文档注明 async 契约 |
| 平台组件 | modules/platforms/tiktok/components/login.py、amazon 各组件、shopee services_export/analytics_export/metrics_selector、miaoshou export | run() 改为 async，内部使用 await page.* |
| 表结构   | modules/core/db/schema.py + 迁移 | 若 CollectionTask 无 started_at/completed_at，则新增两列并更新 router 使用 |
| 前端     | frontend/src/views/collection/（任务列表与详情） | 新增或扩展「任务详情」页/抽屉，展示步骤时间线（基于 getTaskLogs 或新接口返回带 details 的日志列表） |

### 不修改

- 不修改数据同步模块、catalog_files 契约、落盘与登记逻辑。
- 不在此变更中实现 API 采集或采集方式分流（属 add-hybrid-collection-api-playwright）。

### 依赖关系

- 与 add-hybrid-collection-api-playwright 无强依赖；可先于或后于该变更实施。本变更仅提升现有 Playwright 采集链路的可观测性与组件一致性。

## Non-Goals

- 不在此变更中实现 API 采集器或按店铺 API/Playwright 分流。
- 不强制要求组件内每一子步骤都打点；优先保证执行器层「每组件/每数据域」的步骤日志完整。
- 分布式追踪（trace_id/span_id）与告警（邮件/企微）为后续可选增强。

## 与 add-hybrid-collection-api-playwright 的区别

- **add-hybrid-collection-api-playwright**：新增「按店铺选 API 或 Playwright」、实现 Shopee/TikTok API 采集器、落盘与登记契约；不改现有可观测性与组件 run() 契约。
- **本变更（add-collection-step-observability）**：不新增 API 采集；专注「步骤级日志、进度持久化、任务详情步骤时间线、组件 run() 统一为 async」，使脚本出问题时能在界面上看到「哪一步失败」。两者可独立排期与交付。
