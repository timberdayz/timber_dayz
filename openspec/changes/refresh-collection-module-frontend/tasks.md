# Tasks: 数据采集模块前端整体修改

**账号数据源**：新采集系统统一从数据库选择账号。后端 `POST /collection/tasks` 已使用 `account_loader_service`（与 `GET /collection/accounts` 一致），不再使用 `local_accounts.py`。前端账号下拉仅依赖 `GET /collection/accounts`。

## 1. 菜单与路由对齐

- [ ] 1.1 核对「数据采集与管理」下菜单项（采集配置、采集任务、采集历史等）与 backend 提供的模块、权限一致；修正 menuGroups.js 与 router 中 path/name 若与后端或文档不符
- [ ] 1.2 确认路由与 API 前缀（如 /api/collection）无冲突；权限标识与 rolePermissions、后端权限一致

## 2. 采集任务页：快速采集与任务列表

- [ ] 2.1 快速采集表单：平台、账号、数据域、日期范围、调试模式等字段与 POST /collection/tasks 入参一致；提交后正确跳转或刷新任务列表
- [ ] 2.2 **数据域扩展**：快速采集数据域增加「库存 (inventory)」「财务 (finance)」「服务 (services)」，与后端 SUPPORTED_DATA_DOMAINS 一致（至少 inventory 必加，便于采集妙手库存等）
- [ ] 2.3 **日期范围扩展**：增加「最近 30 天」选项；增加「自定义」选项，展开后提供开始/结束日期选择器，提交时把选中的起止日期传给 date_range
- [ ] 2.4 **调试模式说明**：在调试模式开关旁增加 tooltip 或简短文案：有头浏览器会在运行后端的电脑上打开；若任务一直处于「等待」请确认任务是否已开始执行
- [ ] 2.5 任务列表：请求 GET /collection/tasks，展示任务 ID、平台、账号、数据域、进度、current_step/当前数据域、状态、文件数、创建时间；筛选（全部/运行中/排队中/已完成/失败）与后端 params 一致
- [ ] 2.6 列表操作：**取消**对 pending/queued/running 均展示并调用取消 API；继续、重试、「日志」按钮调用对应 API，成功后刷新列表或更新行状态；错误时展示后端返回的 message 或 error_code
- [ ] 2.7 **删除任务**：对终态任务（已完成/失败/已取消/部分成功）增加「删除」按钮，调用 DELETE /collection/tasks/:taskId，删除后刷新列表（依赖后端新增删除接口）
- [ ] 2.8 进度与状态展示：progress、current_step、status、files_collected 等与后端返回字段一致，不出现始终 0% 或错误状态文案

## 3. 任务详情与步骤时间线

- [ ] 3.1 在采集任务列表增加「任务详情」入口（行点击或「查看详情」按钮），打开详情抽屉或页面
- [ ] 3.2 详情上半部分：展示任务元信息（平台、账号、状态、创建/开始/结束时间、总耗时、error_message、completed_domains、failed_domains），数据来源 GET /collection/tasks/:taskId 或列表行数据
- [ ] 3.3 详情下半部分：步骤时间线，调用 GET /collection/tasks/:taskId/logs，按 timestamp 排序；每条展示时间、message、level；若 details 含 step_id/component，展示为步骤名；失败步骤高亮，details.error 可展开
- [ ] 3.4 保留现有「查看日志」弹窗（原始日志流），与任务详情中的步骤时间线互补

## 4. 采集配置与定时

- [ ] 4.1 采集配置列表：CRUD、筛选与后端 GET/POST/PUT/DELETE /collection/configs 一致；「执行」按钮基于配置调用创建任务接口，并在采集任务列表可见新任务
- [ ] 4.2 定时配置：编辑配置时启用定时、执行时间（cron 或预设）与后端 schedule 接口一致；保存后定时任务按约定触发，触发的任务在采集任务列表展示

## 5. 采集历史

- [x] 5.1 历史列表：GET /collection/history，筛选、分页与后端一致（后端入参为 page、page_size、platform、status、start_date、end_date）；响应为 `{ data, total, page, page_size, pages }`，前端使用 `result.data` 作为列表数据、`result.total` 作为总数；统计卡片与后端 TaskStatsResponse 一致（total_tasks、completed、running、failed、success_rate）
- [ ] 5.2 历史详情：点击「详情」展示与任务详情一致的元信息；若有共用组件，可复用任务详情的步骤时间线（通过 getTaskLogs）
- [ ] 5.3 重试：失败任务的「重试」调用 POST /collection/tasks/:taskId/retry，成功后刷新列表

## 6. 实时进度与错误处理

- [ ] 6.1 WebSocket：若后端提供任务进度 WebSocket，前端订阅后更新列表对应行的 progress、current_step、status、files_collected；消息结构与后端约定一致
- [ ] 6.2 若无 WebSocket 或需降级：使用轮询 GET /collection/tasks 或单任务详情，频率合理（如运行中任务每 5–10 秒），避免过度请求
- [ ] 6.3 接口错误时展示后端返回的 message；列表/详情空态、加载态明确，不出现 undefined 或错误字段名

## 7. 后端：删除任务接口（本提案最小必要改动）

- [ ] 7.1 新增 DELETE /api/collection/tasks/:taskId：仅当任务状态为终态（completed / failed / cancelled / partial_success）时允许删除，物理删除任务记录（及关联日志，若为 CASCADE）；非终态返回 400；不存在返回 404

## 8. 验收与文档

- [ ] 8.1 验收：从快速采集发起一次任务，列表展示正确进度与状态，可打开任务详情与步骤时间线，可查看日志弹窗
- [ ] 8.2 验收：快速采集可选库存/财务/服务、最近30天与自定义日期；调试模式旁有说明；pending 任务可取消；终态任务可删除
- [ ] 8.3 验收：从采集配置「执行」创建任务，任务出现在采集任务列表且可观测
- [ ] 8.4 验收：启用定时后，定时触发的任务在采集任务列表可见；采集历史列表与详情、重试正常
- [ ] 8.5 在数据采集相关文档中补充前端入口说明：手动采集（快速采集/配置执行）、自动采集（定时配置）、任务详情与步骤时间线查看方式；任务长期等待与调试模式说明
