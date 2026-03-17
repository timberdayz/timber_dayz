# Tasks: 采集步骤可观测与组件契约统一

## 1. 步骤级日志与进度持久化（后端）

- [x] 1.1 扩展回调接口：在 _execute_collection_task_background 中创建 CollectionExecutorV2 时传入 status_callback；回调签名支持 details（如 status_callback(task_id, progress, message, current_domain=None, details=None) 或单独 step_callback(task_id, details_dict)），details 含 step_id、component、data_domain、success、duration_ms、error
- [x] 1.2 实现回调逻辑：回调内根据 task_id（UUID）查询 CollectionTask 得主键 id；使用**独立 session**（每次写新建 AsyncSession，写后 commit）写入 CollectionTaskLog（level=info/error，message，details）并 update CollectionTask 的 current_step、progress；失败步骤写 level=error 及 details.error
- [x] 1.3 顺序执行路径（execute）：在 executor_v2 成对打点——1.3.1 登录开始（调用回调，details.step_id=login）；1.3.2 登录结束（成功/失败，details 含 success、duration_ms、失败时 error）；1.3.3 各数据域导出开始；1.3.4 各数据域导出结束（成功/失败，含 success、duration_ms、error）；1.3.5 文件处理开始；1.3.6 文件处理结束
- [x] 1.4 并行执行路径（execute_parallel_domains）：注入同一 status_callback，在等价逻辑步骤处打点（登录开始/结束；各数据域在 _execute_single_domain_parallel 或每域任务边界成对打点：单域导出开始、单域导出结束；文件处理开始/结束），与顺序路径语义一致
- [x] 1.5 约定 details 的 JSON 结构（step_id、component、data_domain、success、duration_ms、error），在文档或代码注释中说明，便于前端解析
- [x] 1.6 若 CollectionTask 表无 started_at/completed_at：新增 Alembic 迁移与 schema.py 两列；router 在任务开始写 started_at、终态写 completed_at。同步在 TaskResponse 及任务详情/列表接口使用的响应模型中声明 started_at、completed_at，保证 API 返回开始/结束时间。若表已有列但 schema 未声明，则补全 schema 与响应模型

## 2. 任务详情与步骤时间线（前端）

- [x] 2.1 在采集任务列表页增加「任务详情」入口（如行点击或「查看详情」按钮），打开详情页或抽屉
- [x] 2.2 详情上半部分展示任务元信息：平台、账号、状态、创建/开始/结束时间、总耗时、error_message、completed_domains、failed_domains
- [x] 2.3 详情下半部分展示步骤时间线：调用 getTaskLogs(task_id) 或新接口，按 timestamp 排序；每条展示时间、message、level；若 details 含 step_id/component，展示为步骤名；失败步骤高亮，details.error 可展开
- [x] 2.4 保留现有「查看日志」弹窗（原始日志流），与「任务详情」中的步骤时间线互补

## 3. 组件 run() 统一为 async

- [x] 3.1 将 modules/components/login/base.py、export/base.py、navigation/base.py、date_picker/base.py 中的 run() 改为 async def run(...)，raise NotImplementedError，并在 docstring 中注明「实现必须为 async」
- [x] 3.2 TikTok：login.py 的 run() 改为 async def，内部全部使用 await page.goto、await page.wait_for_timeout 等 async Playwright API
- [x] 3.3 Amazon：login、export、navigation、date_picker 的 run() 改为 async def（若为 skeleton 可保持简单实现）
- [x] 3.4 Shopee：services_export.py、analytics_export.py 的 run() 改为 async def，内部使用 await；metrics_selector 若为 sync 则改为 async（因可能被 call_component 调用）；其余已是 async 的保持不变
- [x] 3.5 Miaoshou：export.py 的 run() 改为 async def，内部使用 await；其他组件若为 sync 则一并改为 async
- [x] 3.6 确认 python_component_adapter 与 executor 中所有 component.run(page) 及 call_component 调用的组件均为 await，且无 sync run 混用

## 4. 验收与文档

（4.1–4.3 需实际执行采集/故意失败/多平台运行后验收，当前尚未执行完整采集。）

- [ ] 4.1 验收：执行一次采集任务（含登录与多数据域），任务详情页能展示按时间排序的步骤时间线，且至少包含「登录」「采集 xxx 域」等步骤及成功/失败状态；顺序与并行两种执行模式均能产生步骤时间线。（**需人工验收**：完整跑通一次采集后打开任务详情查看时间线）
- [ ] 4.2 验收：故意让某一步失败（如错误账号），确认失败步骤在时间线中高亮且 details 中含错误信息。（**需人工验收**：故意失败一次后查看任务详情）
- [ ] 4.3 验收：所有平台（Shopee、TikTok、Miaoshou、Amazon）的 Login/Export 及通过 call_component 调用的组件通过 adapter 调用时无 await 报错、无阻塞。（**需人工验收**：各平台实际跑一次采集确认无报错）
- [x] 4.4 在数据采集相关文档中补充「任务步骤可观测」说明。→ 已新增 `docs/guides/COLLECTION_TASK_STEP_OBSERVABILITY.md`
