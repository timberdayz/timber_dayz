# Data Collection Spec Delta

## ADDED Requirements

### Requirement: Python 组件异步执行

系统 SHALL 仅支持使用异步 Python 组件执行数据采集任务，提供强大的复杂操作支持（悬停、动态下拉框、iframe 遍历、2FA 验证等）。

#### Scenario: 执行 Python 登录组件

- **WHEN** executor_v2 需要执行登录操作
- **THEN** 系统使用 `PythonComponentAdapter` 加载对应平台的登录组件
- **AND** 系统调用异步 `login()` 方法执行登录
- **AND** 系统返回登录结果（success/message）
- **AND** 登录失败时系统记录错误日志

#### Scenario: 执行 Python 导出组件

- **WHEN** executor_v2 需要执行数据域导出（如 orders/products）
- **THEN** 系统根据 platform 和 data_domain 选择对应的 Python 导出组件
- **AND** 系统调用异步 `export()` 方法执行导出
- **AND** 系统返回导出结果（success/file_path）
- **AND** 导出成功时系统将文件注册到 catalog_files 表

#### Scenario: Python 组件异步等待

- **WHEN** Python 组件需要等待页面元素或下载完成
- **THEN** 系统使用 `await page.wait_for_timeout()` 进行异步等待
- **AND** 系统使用 `await page.wait_for_selector()` 等待元素出现
- **AND** 等待超时时系统执行降级策略（如文件系统兜底）

### Requirement: Python 组件适配层

系统 SHALL 提供统一的 Python 组件适配层，封装平台适配器调用和账号预处理。

#### Scenario: 账号密码解密

- **WHEN** 适配层初始化账号信息
- **THEN** 系统检查账号是否包含 `password_encrypted` 字段
- **AND** 如果存在加密密码，系统调用 `EncryptionService.decrypt_password()` 解密
- **AND** 解密成功后系统将明文密码存入 `account["password"]`
- **AND** 解密失败时系统记录警告日志并使用原值（降级策略）

#### Scenario: 平台适配器加载

- **WHEN** 适配层需要获取平台组件
- **THEN** 系统根据 platform 参数选择对应的适配器（ShopeeAdapter/TiktokAdapter/MiaoshouAdapter）
- **AND** 系统创建 ExecutionContext 并初始化适配器
- **AND** 适配器提供 login()/navigation()/exporter() 工厂方法

#### Scenario: 数据域导出组件映射

- **WHEN** 适配层需要获取指定数据域的导出组件
- **THEN** 系统根据 platform 和 data_domain 选择对应的导出组件类
- **AND** Shopee 平台支持 orders/products/finance/services/analytics 等数据域
- **AND** TikTok 平台支持 orders/products/analytics/finance/service 等数据域
- **AND** Miaoshou 平台支持 orders/products/warehouse 等数据域

### Requirement: Python 组件统一执行

系统 SHALL 仅支持 Python 组件执行，移除 YAML 组件支持以避免双维护问题。

#### Scenario: 组件加载和执行

- **WHEN** executor_v2 需要加载组件
- **THEN** 系统使用 `component_loader.load_python_component()` 加载 Python 组件
- **AND** 系统根据组件路径（如 `shopee/products_export`）解析平台和组件名
- **AND** 系统使用 `PythonComponentAdapter` 执行组件
- **AND** 系统返回统一格式的执行结果

#### Scenario: 组件路径解析

- **WHEN** 系统需要加载组件（如 `shopee/products_export`）
- **THEN** 系统解析路径获取平台（shopee）和组件名（products_export）
- **AND** 系统从 `modules/platforms/shopee/components/products_export.py` 加载组件类
- **AND** 系统创建组件实例并执行

#### Scenario: Python 组件元数据读取

- **WHEN** 系统加载 Python 组件类
- **THEN** 系统通过 `inspect` 模块读取类属性（platform、component_type、data_domain）
- **AND** 系统验证元数据完整性（必需字段存在）
- **AND** 系统使用元数据选择正确的组件实例

### Requirement: Python 组件调用机制

系统 SHALL 支持 Python 组件调用其他 Python 组件，替代 YAML 的 `component_call` 机制。

#### Scenario: 导出组件调用日期选择组件

- **WHEN** 导出组件需要选择日期范围
- **THEN** 组件通过适配器获取日期选择组件实例
- **AND** 组件调用 `date_picker.run(page, date_from, date_to)`
- **AND** 日期选择组件执行并返回结果
- **AND** 导出组件继续执行后续逻辑

#### Scenario: 导出组件调用店铺切换组件

- **WHEN** 导出组件需要切换店铺
- **THEN** 组件通过适配器获取店铺切换组件实例
- **AND** 组件调用 `shop_switch.run(page, shop_name)`
- **AND** 店铺切换组件执行并返回结果

#### Scenario: 组件调用参数传递

- **WHEN** Python 组件调用子组件
- **THEN** 参数通过函数参数传递（无需模板替换）
- **AND** 适配层负责参数准备（解密密码、合并参数等）
- **AND** 子组件通过 `run(page, account, params, **kwargs)` 接收参数

### Requirement: ComponentVersion 表迁移

系统 SHALL 支持 ComponentVersion 表从 YAML 文件路径迁移到 Python 文件路径。

#### Scenario: 文件路径字段更新

- **WHEN** 系统迁移 ComponentVersion 记录
- **THEN** 系统将 `file_path` 字段从 `.yaml` 扩展名改为 `.py`
- **AND** 系统保留原路径作为备份（`original_file_path` 字段）
- **AND** 系统添加 `file_type` 字段区分 YAML 和 Python

#### Scenario: 版本记录迁移

- **WHEN** 运行 ComponentVersion 迁移脚本
- **THEN** 系统扫描所有 ComponentVersion 记录
- **AND** 系统将 `.yaml` 路径转换为对应的 `.py` 路径
- **AND** 系统验证目标 Python 文件存在
- **AND** 迁移失败时系统记录错误并跳过该记录

### Requirement: 文件命名标准化

系统 SHALL 使用 `StandardFileName.generate()` 生成标准文件名，与数据同步模块对齐。

#### Scenario: 生成标准文件名

- **WHEN** 导出组件完成数据导出
- **THEN** 系统使用 `StandardFileName.generate()` 生成文件名
- **AND** 文件名格式为 `{platform}_{data_domain}[_{sub_domain}]_{granularity}_{timestamp}.xlsx`
- **AND** 系统不使用旧版 `build_filename()` 方法

#### Scenario: 文件名解析

- **WHEN** 数据同步模块扫描文件
- **THEN** 系统可以使用 `StandardFileName.parse()` 解析文件名
- **AND** 系统提取平台、数据域、粒度、时间戳等元数据

### Requirement: 文件存储路径标准化

系统 SHALL 将采集的文件存储到 `data/raw/YYYY/` 目录，确保数据同步模块可以扫描。

#### Scenario: 文件移动到最终目录

- **WHEN** 导出组件完成文件下载
- **THEN** 系统将文件从 `temp/outputs/` 移动到 `data/raw/YYYY/`
- **AND** 系统根据当前年份创建目录（如 `data/raw/2025/`）
- **AND** 系统删除 `temp/outputs/` 中的临时文件

#### Scenario: 数据同步模块扫描

- **WHEN** 数据同步模块运行扫描任务
- **THEN** 系统扫描 `data/raw/YYYY/` 目录
- **AND** 系统发现新采集的文件
- **AND** 系统不扫描 `temp/outputs/` 目录

### Requirement: 伴生文件格式标准化

系统 SHALL 使用 `MetadataManager.create_meta_file()` 生成 `.meta.json` 伴生文件。

#### Scenario: 生成伴生文件

- **WHEN** 文件移动到最终目录后
- **THEN** 系统调用 `MetadataManager.create_meta_file()` 生成伴生文件
- **AND** 伴生文件名格式为 `{原文件名}.meta.json`
- **AND** 伴生文件与数据文件在同一目录

#### Scenario: 伴生文件内容

- **WHEN** 系统生成伴生文件
- **THEN** 伴生文件包含 `file_info` 节点（文件名、大小、扩展名、创建时间）
- **AND** 伴生文件包含 `business_metadata` 节点（平台、数据域、子域、粒度、日期范围、店铺 ID）
- **AND** 伴生文件包含 `collection_info` 节点（采集方法、平台、账号、店铺 ID、采集时间）

#### Scenario: 数据同步模块读取伴生文件

- **WHEN** 数据同步模块处理文件
- **THEN** 系统读取对应的 `.meta.json` 伴生文件
- **AND** 系统提取业务元数据用于数据入库
- **AND** 伴生文件不存在时系统尝试从文件名解析元数据

### Requirement: 文件注册自动化

系统 SHALL 在采集完成后自动将文件注册到 `catalog_files` 表。

#### Scenario: 自动注册文件

- **WHEN** 文件移动到最终目录并生成伴生文件后
- **THEN** 系统调用 `register_single_file()` 注册文件
- **AND** 系统在 `catalog_files` 表创建记录
- **AND** 系统记录文件路径、平台、数据域等元数据

#### Scenario: 注册失败处理

- **WHEN** 文件注册失败
- **THEN** 系统记录错误日志
- **AND** 系统不删除已移动的文件
- **AND** 系统返回部分成功状态

### Requirement: Python 组件测试工具更新

系统 SHALL 更新测试工具支持 Python 组件加载和执行。

#### Scenario: 加载 Python 组件

- **WHEN** 用户在前端点击"测试组件"
- **THEN** 系统加载指定的 Python 组件类
- **AND** 系统使用 `component_loader.load_python_component()` 加载
- **AND** 系统不再支持 YAML 组件测试

#### Scenario: 执行 Python 组件测试

- **WHEN** 系统加载 Python 组件后
- **THEN** 系统创建 `PythonComponentAdapter` 实例
- **AND** 系统调用 `adapter.execute_component()` 执行组件
- **AND** 系统返回测试结果（成功/失败、执行时间、错误信息）

#### Scenario: 组件版本测试

- **WHEN** 用户测试已注册的组件版本
- **THEN** 系统根据 `file_path` 字段加载 `.py` 文件
- **AND** 系统验证 Python 文件存在
- **AND** 系统执行组件并返回测试结果

### Requirement: Windows 日志兼容性

系统 SHALL 确保所有日志输出在 Windows 控制台正常显示，不使用 emoji 字符。

#### Scenario: 日志输出无 emoji

- **WHEN** 组件执行过程中输出日志
- **THEN** 系统使用 ASCII 符号替代 emoji（如 `[OK]` 替代 ✅）
- **AND** 系统使用 `[ERROR]` 替代 ❌
- **AND** 系统使用 `[WARN]` 替代 ⚠️
- **AND** 系统使用 `[INFO]` 替代 ℹ️
- **AND** Windows 控制台不抛出 UnicodeEncodeError

#### Scenario: 日志输出验证

- **WHEN** 运行 `python scripts/verify_no_emoji.py`
- **THEN** 脚本检查所有 Python 组件文件
- **AND** 报告包含 emoji 的文件和行号
- **AND** 验证通过时返回 0 退出码

## MODIFIED Requirements

### Requirement: 多平台数据采集

系统 SHALL 支持从多个电商平台（包括 Shopee、TikTok、Amazon 和妙手 ERP）进行自动化数据采集，并提供可靠的登录状态检测机制。所有组件执行必须使用异步 Python 组件。

#### Scenario: Shopee 订单数据采集

- **WHEN** 用户使用有效的账号凭证启动 Shopee 平台采集
- **THEN** 系统使用 Playwright 自动化浏览器，执行 Python 登录组件登录 Shopee 卖家中心
- **AND** 系统执行 Python 导航组件跳转到订单导出页面
- **AND** 系统执行 Python 导出组件下载 Excel 文件
- **AND** 系统将文件元数据注册到 catalog_files 表
- **AND** 系统记录采集任务的执行时间和状态

#### Scenario: TikTok 产品数据采集

- **WHEN** 用户启动 TikTok Shop 平台采集
- **THEN** 系统自动化浏览器会话，使用 TikTok 凭证进行身份验证，导出产品数据，并将文件保存到 downloads 目录
- **AND** 系统支持 2FA 验证处理（通过 Python 登录组件）

#### Scenario: 跨平台采集会话持久化

- **WHEN** 采集会话被中断或浏览器关闭
- **THEN** 系统将会话状态保存在会话文件中，可以在不重新认证的情况下恢复采集
- **AND** Python 组件使用 PersistentBrowserManager 管理持久化会话

### Requirement: Playwright API 使用规范（2025-12-21 新增）⭐⭐⭐

系统 SHALL 遵循 Playwright 官方建议，在异步框架中使用 `async_playwright`，避免事件循环冲突和重复实现。所有 Python 平台组件 MUST 使用异步 API。

#### Scenario: 异步框架中的 Playwright 使用

- **WHEN** 在 FastAPI 路由中执行组件测试或批量采集
- **THEN** 系统使用 `async_playwright` API
- **AND** 系统使用 `asyncio.create_task()` 启动后台任务
- **AND** 系统直接使用异步回调传递进度（无需跨线程通信）
- **AND** 系统不使用 `sync_playwright` + threading 模式
- **AND** 系统不使用 subprocess 运行测试（除非是独立脚本）

#### Scenario: Python 组件异步执行

- **WHEN** executor_v2 调用 Python 平台组件
- **THEN** 组件的 `run()` 方法为异步方法（`async def run()`）
- **AND** 所有 Playwright 调用使用 `await` 关键字
- **AND** 组件返回异步结果（`await component.run(page)`）

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

系统 SHALL 仅支持使用 Playwright Inspector API 进行组件录制，提供持久化会话、固定指纹和 Trace 录制功能。Codegen 模式已废弃。

#### Scenario: Inspector 模式录制组件

- **WHEN** 用户在前端启动组件录制
- **THEN** 系统使用 `tools/launch_inspector_recorder.py` 启动录制
- **AND** 系统使用 `PersistentBrowserManager` 创建持久化浏览器上下文
- **AND** 系统使用 `DeviceFingerprintManager` 应用固定设备指纹
- **AND** 系统自动执行 login 组件（如果录制非 login 组件）
- **AND** 系统自动处理弹窗（使用 `UniversalPopupHandler`）
- **AND** 系统启动 Trace 录制（`context.tracing.start()`）
- **AND** 系统打开 Playwright Inspector（`page.pause()`）
- **AND** 用户操作完成后，系统停止 Trace 录制并保存到 `.zip` 文件

#### Scenario: Trace 文件解析生成 Python 组件

- **WHEN** 录制完成并生成 Trace 文件
- **THEN** 系统使用 `TraceParser` 解析 Trace 文件
- **AND** 系统提取用户操作事件（click, fill, goto, wait 等）
- **AND** 系统将事件转换为 Python 组件代码骨架
- **AND** 系统生成包含基本结构的 Python 文件（类定义、run 方法、错误处理）
- **AND** 系统返回 Python 代码给前端编辑器

#### Scenario: Python 组件保存

- **WHEN** 用户编辑完成 Python 组件代码并保存
- **THEN** 系统保存 Python 文件到 `modules/platforms/{platform}/components/{component_name}.py`
- **AND** 系统创建 ComponentVersion 记录
- **AND** 系统验证 Python 代码语法正确性

#### 相关文件

| 文件                                    | 功能                               |
| --------------------------------------- | ---------------------------------- |
| `backend/utils/trace_parser.py`         | Trace 文件解析器                   |
| `tools/launch_inspector_recorder.py`    | Inspector 录制脚本（唯一录制方式） |
| `backend/routers/component_recorder.py` | 录制 API（仅支持 Inspector 模式）  |
