## ADDED Requirements

### Requirement: 端到端采集流程验证
系统 SHALL 提供端到端采集流程验证机制，确保从登录到文件下载注册的完整链路正常工作。

#### Scenario: 完整采集流程验证
- **WHEN** 执行端到端采集测试
- **THEN** 系统完成登录、导航、日期选择、数据导出、文件下载的完整流程
- **AND** 系统将下载的文件保存到data/raw/YYYY/目录，使用标准命名格式
- **AND** 系统将文件注册到catalog_files表，包含完整的元数据（platform_code, shop_id, data_domain, granularity, date_range, file_hash）
- **AND** 系统验证文件路径正确且文件存在
- **AND** 系统生成伴生元数据文件(.meta.json)

#### Scenario: 录制工具功能验证
- **WHEN** 使用录制工具录制组件
- **THEN** 系统自动加载并执行login.yaml组件（如果录制非login组件）
- **AND** 系统启动Playwright Inspector捕获所有用户操作
- **AND** 系统生成完整的YAML配置文件，包含steps、success_criteria、popup_handling、verification_handlers
- **AND** 生成的YAML使用正确的选择器格式（支持role=xxx[name=yyy]格式）

#### Scenario: 组件可执行性验证
- **WHEN** 使用测试工具测试录制的组件
- **THEN** 组件成功执行所有步骤
- **AND** success_criteria验证通过
- **AND** 文件成功下载（对于export组件）

#### Scenario: 文件命名规范验证
- **WHEN** 采集任务完成并保存文件
- **THEN** 文件命名符合标准格式：{platform}_{domain}[_{subdomain}]_{granularity}_{timestamp}.{ext}
- **AND** 文件保存在正确的年度目录：data/raw/YYYY/
- **AND** 伴生元数据文件使用相同的基础名称，后缀为.meta.json

### Requirement: 定时采集配置验证
系统 SHALL 验证APScheduler定时采集任务配置正确且可正常触发。

#### Scenario: 定时任务注册验证
- **WHEN** 创建定时采集配置并启用schedule
- **THEN** 系统在APScheduler中注册定时任务
- **AND** 任务使用正确的Cron表达式
- **AND** 任务ID可追溯到配置ID

#### Scenario: 定时任务触发验证
- **WHEN** 定时任务到达触发时间
- **THEN** 系统自动创建采集任务并执行
- **AND** 任务的trigger_type标记为'scheduled'
- **AND** 任务执行流程与手动触发一致
- **AND** 后端日志记录定时任务触发信息

#### Scenario: 定时任务冲突检测验证
- **WHEN** 定时任务触发时，相同账号已有运行中的任务
- **THEN** 系统跳过本次调度，记录警告日志
- **AND** 不创建重复的采集任务

### Requirement: Playwright API 使用规范（2025-12-21 新增）⭐⭐⭐

系统 SHALL 遵循 Playwright 官方建议，在异步框架中使用 `async_playwright`，避免事件循环冲突和重复实现。

#### Scenario: 异步框架中的 Playwright 使用

- **WHEN** 在 FastAPI 路由中执行组件测试或批量采集
- **THEN** 系统使用 `async_playwright` API
- **AND** 系统使用 `asyncio.create_task()` 启动后台任务
- **AND** 系统直接使用异步回调传递进度（无需跨线程通信）
- **AND** 系统不使用 `sync_playwright` + threading 模式
- **AND** 系统不使用 subprocess 运行测试（除非是独立脚本）

#### Scenario: 独立脚本中的 Playwright 使用

- **WHEN** 在独立命令行脚本中执行 Playwright 操作
- **THEN** 系统可以使用 `sync_playwright` API
- **AND** 系统使用 `asyncio.run()` 包装异步入口（如果使用 async_playwright）
- **AND** 系统使用 subprocess 启动独立进程（如果需要完全隔离，如录制工具）

#### Scenario: 并发执行多个 Playwright 任务

- **WHEN** 需要并发执行多个数据域采集或组件测试
- **THEN** 系统使用 `async_playwright` + `asyncio.gather()`
- **AND** 系统不使用多个 subprocess 或 threading
- **AND** 系统通过 `max_parallel` 参数控制并发数

#### Scenario: 实时进度反馈

- **WHEN** 需要实时推送测试或采集进度到前端
- **THEN** 系统使用异步回调直接发送 WebSocket 消息
- **AND** 系统不使用 `asyncio.run_coroutine_threadsafe`（如果已在异步上下文中）
- **AND** 系统不使用文件轮询或进程间通信

#### 决策原则

**API 选择**：
- ✅ **异步框架（FastAPI）** → `async_playwright`
- ✅ **独立脚本** → `async_playwright` + `asyncio.run()` 或 `sync_playwright`
- ❌ **禁止**：在异步框架中使用 `sync_playwright`

**执行方式选择**：
- ✅ **异步框架中** → `async_playwright` + `asyncio.create_task()`
- ✅ **独立脚本** → `sync_playwright` + subprocess（如果需要隔离）
- ❌ **禁止**：在异步框架中使用 `sync_playwright` + threading

**历史教训**：
- ⚠️ **避免重复实现**：不要为了隔离而隔离，如果框架支持异步，直接使用异步
- ⚠️ **遵循官方建议**：Playwright 官方明确建议在异步框架中使用 `async_playwright`
- ⚠️ **避免过度设计**：简单的异步方案往往比复杂的线程/进程方案更好

### Requirement: Inspector API 录制模式（2025-12-23 新增）⭐⭐⭐

系统 SHALL 支持使用 Playwright Inspector API 进行组件录制，提供持久化会话、固定指纹和 Trace 录制功能。

#### Scenario: Inspector 模式录制组件

- **WHEN** 用户选择使用 Inspector 模式录制组件
- **THEN** 系统使用 `PersistentBrowserManager` 创建持久化浏览器上下文
- **AND** 系统使用 `DeviceFingerprintManager` 应用固定设备指纹
- **AND** 系统自动执行 login 组件（如果录制非 login 组件）
- **AND** 系统自动处理弹窗（使用 `UniversalPopupHandler`）
- **AND** 系统启动 Trace 录制（`context.tracing.start()`）
- **AND** 系统打开 Playwright Inspector（`page.pause()`）
- **AND** 用户操作完成后，系统停止 Trace 录制并保存到 `.zip` 文件

#### Scenario: Trace 文件解析

- **WHEN** 录制完成并生成 Trace 文件
- **THEN** 系统使用 `TraceParser` 解析 Trace 文件
- **AND** 系统提取用户操作事件（click, fill, goto, wait 等）
- **AND** 系统将事件转换为组件步骤格式（YAML）
- **AND** 系统保存步骤到 JSON 文件
- **AND** 系统返回步骤列表给前端

#### Scenario: 录制模式切换

- **WHEN** 需要在 Codegen 和 Inspector 模式之间切换
- **THEN** 系统通过 `RECORDING_MODE` 配置变量控制
- **AND** 两种模式输出相同格式的步骤列表
- **AND** 前端无需修改即可兼容两种模式

#### 功能对比

| 特性 | Codegen 模式 | Inspector 模式 |
|------|-------------|---------------|
| 持久化会话 | ❌ | ✅ |
| 固定指纹 | ❌ | ✅ |
| 自动登录 | ❌ | ✅ |
| 弹窗处理 | ❌ | ✅ |
| 步骤提取 | 代码解析 | Trace 解析 |
| 调试能力 | 有限 | 完整 Trace 回放 |

#### 相关文件

| 文件 | 功能 |
|------|------|
| `backend/utils/trace_parser.py` | Trace 文件解析器 |
| `tools/launch_inspector_recorder.py` | Inspector 录制脚本 |
| `backend/routers/component_recorder.py` | 录制 API（双模式支持） |
