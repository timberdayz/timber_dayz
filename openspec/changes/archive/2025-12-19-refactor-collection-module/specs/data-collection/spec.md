# 数据采集能力 - 规格变更（方案B：组件驱动架构）

## ADDED Requirements

### Requirement: 组件驱动的采集架构

系统 SHALL 采用组件驱动架构进行数据采集，将采集流程拆分为可复用的 YAML 配置组件。

#### Scenario: 组件加载

- **WHEN** 采集执行器需要执行采集任务
- **THEN** 系统从 `config/collection_components/{platform}/` 加载相应组件
- **AND** 系统验证组件 YAML 格式正确
- **AND** 系统解析组件依赖关系

#### Scenario: 组件执行

- **WHEN** 采集执行器执行组件
- **THEN** 系统按照组件定义的步骤顺序执行 Playwright 操作
- **AND** 系统替换组件中的变量模板（如 `{{account.username}}`）
- **AND** 系统在每个步骤后更新任务进度

#### Scenario: 组件嵌套调用

- **WHEN** 组件步骤包含 `action: component_call`
- **THEN** 系统加载并执行被调用的组件
- **AND** 系统传递参数给被调用组件
- **AND** 被调用组件执行完成后返回父组件继续执行

### Requirement: 组件录制工具

系统 SHALL 提供 CLI 组件录制工具，支持录制单个组件的 Playwright 操作并输出为 YAML 配置。

#### Scenario: 启动组件录制

- **WHEN** 管理员运行 `python tools/record_component.py --platform shopee --component orders_export --account MyStore`
- **THEN** 系统启动浏览器（headed 模式）
- **AND** 系统自动执行前置组件（如 login、navigation）
- **AND** 系统开启 Playwright Inspector 进入录制模式

#### Scenario: 生成组件配置

- **WHEN** 管理员在 Inspector 中完成录制并关闭
- **THEN** 系统解析录制的操作序列
- **AND** 系统转换为结构化 YAML 格式
- **AND** 系统保存到 `config/collection_components/{platform}/{component}.yaml`

### Requirement: Playwright官方API使用规范（2025-12-17新增）⭐

系统 SHALL 优先使用 Playwright 官方 API 和官方工具，不创建自定义实现。

#### Scenario: 元素定位

- **WHEN** 系统需要定位页面元素
- **THEN** 系统优先使用 `get_by_role/label/text` 等官方语义化API
- **AND** 系统不创建自定义选择器修复逻辑
- **AND** 仅在官方API无法满足时使用通用 `locator()`

#### Scenario: 页面加载等待

- **WHEN** 系统导航到新页面
- **THEN** 系统等待 DOM 内容加载完成（domcontentloaded）
- **AND** 系统等待网络空闲（networkidle，最多10秒）
- **AND** 系统额外等待1秒确保JavaScript渲染完成

#### Scenario: 元素交互

- **WHEN** 系统需要点击或填充元素
- **THEN** 系统等待元素可见（visible state）
- **AND** 系统滚动元素到视图（scroll_into_view_if_needed）
- **AND** 系统执行交互操作（click/fill）

#### Scenario: 禁止行为

- **WHEN** 开发者实现Playwright相关功能
- **THEN** 系统不得创建 `_fix_selector()` 方法
- **AND** 系统不得创建 `_get_smart_locator()` 多策略降级
- **AND** 系统不得手动转换选择器格式（如 role=xxx 转 CSS）
- **AND** 系统不得绕过官方API直接操作底层实现

### Requirement: API 驱动的采集任务管理

系统 SHALL 提供 RESTful API 接口，支持通过 HTTP 请求管理数据采集任务。

#### Scenario: 创建采集任务

- **WHEN** 管理员调用 `POST /api/collection/tasks` 并提供 platform、account_ids、data_domains、sub_domain、granularity、date_range 参数
- **THEN** 系统创建采集任务记录，状态为 pending
- **AND** 系统启动后台任务执行采集
- **AND** 系统返回任务 ID 供后续查询

#### Scenario: 获取任务列表

- **WHEN** 管理员调用 `GET /api/collection/tasks` 并可选提供 status、platform 筛选参数
- **THEN** 系统返回任务列表，支持分页
- **AND** 每个任务包含 id、platform、account_id、status、progress、current_step、created_at 等字段

#### Scenario: 取消运行中任务

- **WHEN** 管理员调用 `DELETE /api/collection/tasks/{id}` 取消一个运行中的任务
- **THEN** 系统将任务状态标记为 cancelled
- **AND** 系统停止后台任务执行（在下一个检查点）
- **AND** 系统保留已采集的文件

### Requirement: 采集配置管理

系统 SHALL 支持通过 API 创建和管理采集配置模板，用于快速启动采集任务和定时调度。

#### Scenario: 创建采集配置

- **WHEN** 管理员调用 `POST /api/collection/configs` 并提供配置参数
- **THEN** 系统创建配置记录并返回配置 ID
- **AND** 配置参数包含：name、platform、account_ids、data_domains、sub_domain、granularity、date_range_type、schedule_cron

#### Scenario: 更新采集配置

- **WHEN** 管理员调用 `PUT /api/collection/configs/{id}` 更新配置
- **THEN** 系统更新配置记录
- **AND** 如果配置有关联的定时任务，系统同步更新定时任务

#### Scenario: 删除采集配置

- **WHEN** 管理员调用 `DELETE /api/collection/configs/{id}` 删除配置
- **THEN** 系统删除配置记录
- **AND** 如果配置有关联的定时任务，系统同步删除定时任务
- **AND** 历史执行记录保留，不受影响

### Requirement: 账号信息脱敏访问

系统 SHALL 提供账号列表 API，返回脱敏后的账号信息供前端展示和选择。

#### Scenario: 获取账号列表

- **WHEN** 管理员调用 `GET /api/collection/accounts`
- **THEN** 系统从 local_accounts.py 读取账号配置
- **AND** 系统返回脱敏后的账号列表（包含 account_id、platform、store_name，不包含 password）

#### Scenario: 按平台筛选账号

- **WHEN** 管理员调用 `GET /api/collection/accounts?platform=shopee`
- **THEN** 系统仅返回指定平台的账号列表

### Requirement: WebSocket 实时状态推送

系统 SHALL 通过 WebSocket 实时推送采集任务的执行状态和进度。

#### Scenario: 订阅任务状态

- **WHEN** 前端连接 `WS /ws/collection/{task_id}`
- **THEN** 系统接受 WebSocket 连接并注册订阅
- **AND** 系统在任务状态变化时推送消息

#### Scenario: 接收进度更新

- **WHEN** 采集任务执行进度更新
- **THEN** 系统通过 WebSocket 推送进度消息
- **AND** 消息格式为 `{type: "progress", progress: 50, current_step: "正在导出数据..."}`

#### Scenario: 接收日志消息

- **WHEN** 采集任务产生日志
- **THEN** 系统通过 WebSocket 推送日志消息
- **AND** 消息格式为 `{type: "log", level: "info", message: "文件下载完成"}`

#### Scenario: 接收完成通知

- **WHEN** 采集任务完成（成功或失败）
- **THEN** 系统通过 WebSocket 推送完成消息
- **AND** 消息格式为 `{type: "complete", status: "completed", files_collected: 5}`

#### Scenario: 验证码暂停通知

- **WHEN** 采集过程中检测到验证码
- **THEN** 系统暂停采集任务
- **AND** 系统通过 WebSocket 推送验证码通知
- **AND** 消息格式为 `{type: "verification_required", message: "检测到验证码，请手动处理"}`

#### Scenario: WebSocket 断线重连

- **WHEN** WebSocket 连接断开
- **THEN** 前端使用指数退避策略自动重连
- **AND** 重连成功后继续接收最新状态

### Requirement: 定时自动采集

系统 SHALL 支持配置定时采集任务，按照 Cron 表达式自动触发采集。

#### Scenario: 启用定时采集

- **WHEN** 管理员创建或更新配置时设置 schedule_enabled=true 和 schedule_cron
- **THEN** 系统创建定时任务，按照 Cron 表达式定时触发
- **AND** 定时任务信息持久化到数据库

#### Scenario: 定时任务触发

- **WHEN** 定时任务到达执行时间
- **THEN** 系统自动创建采集任务
- **AND** 任务的 trigger_type 标记为 "scheduled"
- **AND** 系统按照配置的参数执行采集

#### Scenario: 禁用定时采集

- **WHEN** 管理员更新配置设置 schedule_enabled=false
- **THEN** 系统暂停定时任务
- **AND** 已暂停的定时任务不会触发

#### Scenario: 定时任务冲突处理

- **WHEN** 定时任务触发时，同一账号已有运行中的任务
- **THEN** 系统跳过本次执行
- **AND** 系统记录跳过原因到日志

### Requirement: 采集历史查询

系统 SHALL 提供采集历史查询 API，支持分页、筛选和统计。

#### Scenario: 查询历史记录

- **WHEN** 管理员调用 `GET /api/collection/history`
- **THEN** 系统返回历史记录列表，默认按时间倒序
- **AND** 支持分页参数 page、page_size

#### Scenario: 筛选历史记录

- **WHEN** 管理员调用 `GET /api/collection/history?platform=shopee&status=completed`
- **THEN** 系统返回符合筛选条件的历史记录

#### Scenario: 获取统计数据

- **WHEN** 管理员调用 `GET /api/collection/history/stats`
- **THEN** 系统返回统计数据
- **AND** 统计数据包含：总任务数、成功数、失败数、成功率、按平台分布

### Requirement: 代理IP接口预留

系统 SHALL 定义代理IP提供者接口，支持后续集成代理IP池服务。

#### Scenario: 获取代理配置

- **WHEN** 采集执行器需要代理IP时
- **THEN** 系统调用 ProxyProvider.get_proxy(platform, region)
- **AND** 如果返回代理配置，系统在浏览器上下文中应用代理
- **AND** 如果返回 None，系统不使用代理

#### Scenario: 报告代理失败

- **WHEN** 使用代理后采集失败
- **THEN** 系统调用 ProxyProvider.report_failure(proxy, reason)
- **AND** 代理提供者可据此标记失效代理

### Requirement: 任务恢复与重试

系统 SHALL 支持采集任务的恢复和重试，处理中断、失败和暂停的任务。

#### Scenario: 重试失败任务

- **WHEN** 管理员调用 `POST /api/collection/tasks/{id}/retry` 重试一个失败或中断的任务
- **THEN** 系统创建新任务，复制原任务参数
- **AND** 新任务的 `parent_task_id` 指向原任务
- **AND** 系统启动新任务执行

#### Scenario: 继续暂停任务

- **WHEN** 管理员调用 `POST /api/collection/tasks/{id}/resume` 继续一个暂停的任务
- **THEN** 系统将任务状态从 paused 改为 running
- **AND** 系统从暂停点继续执行

#### Scenario: 服务重启恢复

- **WHEN** 服务重启时存在 running 状态的任务
- **THEN** 系统将这些任务标记为 interrupted
- **AND** 系统记录中断原因到日志
- **AND** 管理员可以手动重试中断的任务

### Requirement: 远程验证码处理

系统 SHALL 支持在 Docker headless 环境中远程处理验证码。

#### Scenario: 检测验证码

- **WHEN** 采集过程中检测到验证码元素
- **THEN** 系统暂停任务执行
- **AND** 系统保存当前页面截图到 `temp/screenshots/{task_id}/`
- **AND** 系统更新任务状态为 paused

#### Scenario: 通知前端验证码

- **WHEN** 任务因验证码暂停
- **THEN** 系统通过 WebSocket 推送 `verification_required` 消息
- **AND** 消息包含 `screenshot_url` 和 `verification_type`
- **AND** 前端显示验证码处理弹窗

#### Scenario: 提交验证码

- **WHEN** 管理员调用 `POST /api/collection/tasks/{id}/verify` 提交验证码
- **THEN** 系统在浏览器中填入验证码并提交
- **AND** 系统将任务状态改为 running
- **AND** 系统继续执行采集任务

#### Scenario: 获取验证码截图

- **WHEN** 前端调用 `GET /api/collection/tasks/{id}/screenshot`
- **THEN** 系统返回保存的截图文件
- **AND** 截图用于在前端显示验证码内容

### Requirement: 长时间任务处理

系统 SHALL 实现长时间运行任务的超时控制和状态管理。

#### Scenario: 组件执行超时

- **WHEN** 单个组件执行时间超过 5 分钟（可配置）
- **THEN** 系统终止组件执行
- **AND** 系统保存超时截图
- **AND** 系统将任务标记为 failed，错误原因为"组件超时"

#### Scenario: 任务总超时

- **WHEN** 整个任务执行时间超过 30 分钟（可配置）
- **THEN** 系统终止任务执行
- **AND** 系统保存已采集的文件
- **AND** 系统将任务标记为 failed，错误原因为"任务超时"

### Requirement: 并发控制

系统 SHALL 实现采集任务的并发控制，防止资源竞争和账号冲突。

#### Scenario: 同账号互斥

- **WHEN** 创建任务时，同一账号已有运行中的任务
- **THEN** 系统拒绝创建新任务
- **AND** 系统返回错误信息"账号已有运行中的任务"

#### Scenario: 总并发数限制

- **WHEN** 创建任务时，运行中的任务数已达到限制（默认 3）
- **THEN** 系统将新任务状态设为 queued（排队）
- **AND** 系统在有任务完成后自动启动排队任务

### Requirement: 采集文件处理与注册

系统 SHALL 自动处理采集到的文件，生成标准命名并注册到数据目录。

#### Scenario: 文件临时存储

- **WHEN** 浏览器下载数据文件
- **THEN** 系统将文件保存到 `temp/downloads/{task_uuid}/`
- **AND** 系统记录原始文件名

#### Scenario: 文件标准化处理

- **WHEN** 采集任务完成数据导出
- **THEN** 系统使用 `file_naming.StandardFileName` 生成标准文件名
- **AND** 系统将文件移动到 `data/raw/YYYY/`
- **AND** 系统生成 `.meta.json` 伴生元数据文件

#### Scenario: 文件自动注册

- **WHEN** 文件移动到 `data/raw/` 完成
- **THEN** 系统调用 `register_single_file()` 注册到 `catalog_files`
- **AND** 注册信息包含：file_path、source、platform、data_domain、granularity

## MODIFIED Requirements

### Requirement: 采集状态监控

系统 SHALL 提供数据采集操作的实时状态监控，支持 API 查询和 WebSocket 推送。

#### Scenario: 采集进度跟踪

- **WHEN** 采集操作正在进行中
- **THEN** 系统更新采集状态到数据库（progress、current_step）
- **AND** 系统通过 WebSocket 推送进度信息
- **AND** 系统通过 API 端点提供状态查询

#### Scenario: 采集错误处理

- **WHEN** 由于网络错误或身份验证失败导致采集失败
- **THEN** 系统记录错误详情到 collection_task_logs 表
- **AND** 系统更新任务状态为 failed
- **AND** 系统通过 WebSocket 推送失败通知
- **AND** 系统保存错误截图（如果可能）

#### Scenario: 采集任务重试

- **WHEN** 采集任务失败且未超过最大重试次数
- **THEN** 系统等待配置的重试间隔后自动重试
- **AND** 系统记录重试次数和原因

### Requirement: 多平台数据采集

系统 SHALL 支持从多个电商平台（包括 Shopee、TikTok 和妙手ERP）进行自动化数据采集。

#### Scenario: Shopee订单数据采集

- **WHEN** 用户通过 API 启动 Shopee 平台采集任务
- **THEN** 系统创建采集任务记录
- **AND** 系统加载 Shopee 平台组件（login、navigation、date_picker、orders_export）
- **AND** 系统按顺序执行组件完成登录、导航、日期选择、数据导出
- **AND** 系统将文件保存到 `data/raw/YYYY/` 并注册到 `catalog_files`

#### Scenario: TikTok产品数据采集

- **WHEN** 用户通过 API 启动 TikTok Shop 平台采集任务
- **THEN** 系统创建采集任务记录
- **AND** 系统加载 TikTok 平台组件执行采集
- **AND** 系统导出产品数据并保存注册

#### Scenario: 妙手ERP数据采集

- **WHEN** 用户通过 API 启动妙手ERP平台采集任务
- **THEN** 系统创建采集任务记录
- **AND** 系统加载妙手ERP平台组件执行采集
- **AND** 系统导出数据并保存注册

#### Scenario: 跨平台采集会话持久化

- **WHEN** 采集会话被中断或浏览器关闭
- **THEN** 系统将会话状态保存在会话文件中
- **AND** 下次采集可以在不重新认证的情况下恢复

### Requirement: 数据域支持

系统 SHALL 支持多种数据域和时间粒度的采集。

#### Scenario: 数据域选择

- **WHEN** 用户创建采集任务
- **THEN** 系统支持选择以下数据域：orders、products、services、analytics、finance、inventory
- **AND** 当选择 services 数据域时，系统支持选择子域：agent、ai_assistant

> 注：`traffic` 域已废弃，统一使用 `analytics`

#### Scenario: 时间粒度选择

- **WHEN** 用户创建采集任务
- **THEN** 系统支持选择时间粒度：daily（日报）、weekly（周报）、monthly（月报）
- **AND** 系统根据粒度生成对应的文件命名

### Requirement: 弹窗自动处理

系统 SHALL 自动检测并关闭采集过程中出现的意外弹窗或通知弹窗。

#### Scenario: 通用弹窗处理

- **WHEN** 采集执行过程中出现弹窗
- **THEN** 系统使用通用弹窗处理器自动检测并关闭
- **AND** 系统支持30+通用关闭选择器（如 `[aria-label="关闭"]`, `.modal-close`, `button:has-text("关闭")`）
- **AND** 系统在主页面和所有iframe中查找弹窗
- **AND** 系统支持ESC键兜底关闭（如果检测到遮罩层）

#### Scenario: 平台特定弹窗处理

- **WHEN** 平台特定弹窗出现（如Shopee问卷弹窗、妙手ERP通知弹窗）
- **THEN** 系统从 `config/collection_components/{platform}/popup_config.yaml` 加载平台特定选择器
- **AND** 系统合并通用选择器和平台特定选择器
- **AND** 系统使用平台特定的轮询策略（max_rounds, interval_ms, watch_ms）

#### Scenario: 组件级弹窗处理

- **WHEN** 组件配置了 `popup_handling.auto_close: true`
- **THEN** 系统在组件执行前自动检查并关闭弹窗（如果配置了 `check_before_steps`）
- **AND** 系统在每个步骤执行后检查弹窗（如果步骤配置了 `popup_handling.check_after`）
- **AND** 系统在组件执行后最终检查弹窗（如果配置了 `check_after_steps`）

#### Scenario: 错误时弹窗处理

- **WHEN** 步骤执行失败
- **THEN** 系统检查弹窗（如果组件配置了 `check_on_error: true`）
- **AND** 系统尝试关闭弹窗后重试步骤（可能是弹窗遮挡导致失败）

#### Scenario: 弹窗关闭策略

- **WHEN** 检测到弹窗
- **THEN** 系统优先尝试点击关闭按钮（遍历所有选择器）
- **AND** 如果按钮未命中，系统检测遮罩层并尝试ESC键关闭
- **AND** 系统使用轮询策略（最多20轮，每轮间隔300ms，总观察时间8秒）
- **AND** 系统记录关闭的弹窗数量到日志

### Requirement: WebSocket连接认证

系统 SHALL 对WebSocket连接进行JWT Token认证，防止未授权访问。

#### Scenario: WebSocket连接认证成功

- **WHEN** 客户端使用有效JWT Token连接 `/ws/collection/{task_id}?token=xxx`
- **THEN** 系统验证Token有效性
- **AND** 系统接受WebSocket连接
- **AND** 系统注册连接到任务状态订阅

#### Scenario: WebSocket连接认证失败

- **WHEN** 客户端使用无效或过期JWT Token连接WebSocket
- **THEN** 系统验证Token失败
- **AND** 系统关闭连接，返回code=4001
- **AND** 系统记录认证失败日志

### Requirement: 系统健康监控

系统 SHALL 提供健康检查端点，返回系统运行状态。

#### Scenario: 健康检查成功

- **WHEN** 调用 `GET /api/collection/health`
- **THEN** 系统返回健康状态信息
- **AND** 状态包含：运行中任务数、排队任务数、最大并发数
- **AND** 状态包含：浏览器池状态（活跃数量、空闲数量）
- **AND** 状态包含：清理任务状态（上次执行时间、下次执行时间）

#### Scenario: 健康检查异常

- **WHEN** 系统内部出现错误（如数据库连接失败）
- **THEN** 系统返回不健康状态
- **AND** 状态包含错误信息

### Requirement: 临时文件自动清理

系统 SHALL 自动清理过期的临时文件，防止磁盘空间耗尽。

#### Scenario: 下载文件清理

- **WHEN** 下载文件超过保留期限（默认7天）
- **THEN** 系统在定时清理任务中删除过期文件
- **AND** 系统记录清理日志

#### Scenario: 截图文件清理

- **WHEN** 截图文件超过保留期限（默认30天）
- **THEN** 系统在定时清理任务中删除过期文件
- **AND** 系统记录清理日志

#### Scenario: 定时清理任务执行

- **WHEN** 到达清理任务执行时间（默认每天凌晨3点）
- **THEN** 系统执行临时文件清理
- **AND** 系统更新清理任务执行时间记录

### Requirement: 浏览器进程资源管理

系统 SHALL 管理浏览器进程资源，防止进程泄漏。

#### Scenario: 启动时清理孤儿进程

- **WHEN** 服务启动时
- **THEN** 系统检测孤儿浏览器进程（无主的chromium/chrome进程）
- **AND** 系统终止孤儿进程
- **AND** 系统记录清理日志

#### Scenario: 定期检查浏览器进程

- **WHEN** 到达定期检查时间（每小时）
- **THEN** 系统检查浏览器进程状态
- **AND** 系统清理不在管理列表中的孤儿进程

#### Scenario: 任务结束时释放资源

- **WHEN** 采集任务完成或失败
- **THEN** 系统关闭任务使用的浏览器上下文
- **AND** 系统从管理列表中移除进程

### Requirement: 任务状态并发安全

系统 SHALL 使用乐观锁保证任务状态更新的并发安全。

#### Scenario: 乐观锁更新成功

- **WHEN** 更新任务状态时当前状态与期望状态一致
- **THEN** 系统成功更新状态
- **AND** 系统返回更新成功

#### Scenario: 乐观锁更新冲突

- **WHEN** 更新任务状态时当前状态与期望状态不一致（被其他进程修改）
- **THEN** 系统拒绝更新
- **AND** 系统返回更新失败
- **AND** 系统记录冲突日志

### Requirement: 排队任务自动启动

系统 SHALL 在有任务完成时自动启动排队中的任务。

#### Scenario: 任务完成后启动排队任务

- **WHEN** 一个运行中的任务完成（成功或失败）
- **AND** 当前运行中任务数小于最大并发数
- **AND** 存在排队中的任务
- **THEN** 系统获取最早创建的排队任务
- **AND** 系统使用乐观锁将其状态更新为running
- **AND** 系统启动任务执行

#### Scenario: 无排队任务时不操作

- **WHEN** 一个运行中的任务完成
- **AND** 不存在排队中的任务
- **THEN** 系统不执行任何操作

### Requirement: 文件注册原子性

系统 SHALL 保证文件移动和catalog注册的原子性，防止数据不一致。

#### Scenario: 文件处理成功

- **WHEN** 采集到的文件需要处理
- **THEN** 系统在事务中执行：移动文件 → 生成元数据 → 注册catalog
- **AND** 所有步骤成功后提交事务

#### Scenario: 文件处理失败回滚

- **WHEN** 文件处理过程中任何步骤失败（如catalog注册失败）
- **THEN** 系统回滚所有操作
- **AND** 系统将已移动的文件恢复到原位置
- **AND** 系统删除已生成的元数据文件
- **AND** 系统记录失败原因

### Requirement: 组件YAML安全验证

系统 SHALL 验证组件YAML文件的安全性，防止注入攻击。

#### Scenario: 安全验证通过

- **WHEN** 加载组件YAML时
- **AND** YAML内容不包含危险模式
- **THEN** 系统正常加载组件

#### Scenario: 检测到危险selector

- **WHEN** 加载组件YAML时
- **AND** selector包含危险模式（如javascript:、data:、on*事件）
- **THEN** 系统拒绝加载组件
- **AND** 系统记录安全警告日志

#### Scenario: 检测到YAML格式异常

- **WHEN** 加载组件YAML时
- **AND** YAML格式不正确或包含异常结构
- **THEN** 系统拒绝加载组件
- **AND** 系统记录格式错误日志
