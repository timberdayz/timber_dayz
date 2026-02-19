# Tasks: 数据采集模块前端整体修改

## 1. 菜单与路由对齐

- [ ] 1.1 核对「数据采集与管理」下菜单项（采集配置、采集任务、采集历史等）与 backend 提供的模块、权限一致；修正 menuGroups.js 与 router 中 path/name 若与后端或文档不符
- [ ] 1.2 确认路由与 API 前缀（如 /api/collection）无冲突；权限标识与 rolePermissions、后端权限一致

## 2. 采集任务页：快速采集与任务列表

- [ ] 2.1 快速采集表单：平台、账号、数据域、日期范围、调试模式等字段与 POST /collection/tasks 入参一致；提交后正确跳转或刷新任务列表
- [ ] 2.2 任务列表：请求 GET /collection/tasks，展示任务 ID、平台、账号、数据域、进度、current_step/当前数据域、状态、文件数、创建时间；筛选（全部/运行中/排队中/已完成/失败）与后端 params 一致
- [ ] 2.3 列表操作：取消、继续、重试、「日志」按钮调用对应 API，成功后刷新列表或更新行状态；错误时展示后端返回的 message 或 error_code
- [ ] 2.4 进度与状态展示：progress、current_step、status、files_collected 等与后端返回字段一致，不出现始终 0% 或错误状态文案

## 3. 任务详情与步骤时间线

- [ ] 3.1 在采集任务列表增加「任务详情」入口（行点击或「查看详情」按钮），打开详情抽屉或页面
- [ ] 3.2 详情上半部分：展示任务元信息（平台、账号、状态、创建/开始/结束时间、总耗时、error_message、completed_domains、failed_domains），数据来源 GET /collection/tasks/:taskId 或列表行数据
- [ ] 3.3 详情下半部分：步骤时间线，调用 GET /collection/tasks/:taskId/logs，按 timestamp 排序；每条展示时间、message、level；若 details 含 step_id/component，展示为步骤名；失败步骤高亮，details.error 可展开
- [ ] 3.4 保留现有「查看日志」弹窗（原始日志流），与任务详情中的步骤时间线互补

## 4. 采集配置与定时

- [ ] 4.1 采集配置列表：CRUD、筛选与后端 GET/POST/PUT/DELETE /collection/configs 一致；「执行」按钮基于配置调用创建任务接口，并在采集任务列表可见新任务
- [ ] 4.2 定时配置：编辑配置时启用定时、执行时间（cron 或预设）与后端 schedule 接口一致；保存后定时任务按约定触发，触发的任务在采集任务列表展示

## 5. 采集历史

- [ ] 5.1 历史列表：GET /collection/history，筛选、分页与后端一致；列展示任务 ID、平台、账号、数据域、状态、文件数、耗时、完成时间等
- [ ] 5.2 历史详情：点击「详情」展示与任务详情一致的元信息；若有共用组件，可复用任务详情的步骤时间线（通过 getTaskLogs）
- [ ] 5.3 重试：失败任务的「重试」调用 POST /collection/tasks/:taskId/retry，成功后刷新列表

## 6. 实时进度与错误处理

- [ ] 6.1 WebSocket：若后端提供任务进度 WebSocket，前端订阅后更新列表对应行的 progress、current_step、status、files_collected；消息结构与后端约定一致
- [ ] 6.2 若无 WebSocket 或需降级：使用轮询 GET /collection/tasks 或单任务详情，频率合理（如运行中任务每 5–10 秒），避免过度请求
- [ ] 6.3 接口错误时展示后端返回的 message；列表/详情空态、加载态明确，不出现 undefined 或错误字段名

## 7. 验收与文档

- [ ] 7.1 验收：从快速采集发起一次任务，列表展示正确进度与状态，可打开任务详情与步骤时间线，可查看日志弹窗
- [ ] 7.2 验收：从采集配置「执行」创建任务，任务出现在采集任务列表且可观测
- [ ] 7.3 验收：启用定时后，定时触发的任务在采集任务列表可见；采集历史列表与详情、重试正常
- [ ] 7.4 在数据采集相关文档中补充前端入口说明：手动采集（快速采集/配置执行）、自动采集（定时配置）、任务详情与步骤时间线查看方式
