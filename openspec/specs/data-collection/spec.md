# 数据采集能力

## Purpose

系统应支持从多个电商平台（包括Shopee、TikTok、Amazon和妙手ERP）进行自动化数据采集，并将采集的文件注册到catalog_files表进行元数据索引管理。
## Requirements
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

### Requirement: Playwright反检测技术
系统 SHALL 使用Playwright而非Selenium进行数据采集，以避免反机器人检测机制；主采集执行器 SHALL 按账号应用浏览器指纹并按账号持久化/复用会话，与业界「一账号一指纹、会话复用」一致。

#### Scenario: 浏览器指纹管理
- **WHEN** 创建Playwright浏览器实例（含主采集执行器）
- **THEN** 系统按 platform 与 account_id 应用该账号的浏览器指纹，以避免多账号同指纹或随机指纹带来的检测风险
- **AND** 主采集执行器创建 context 时**统一**使用 DeviceFingerprintManager 获取或生成该账号的指纹（user_agent、viewport、locale、timezone_id 等），与录制、PersistentBrowserManager 一致

#### Scenario: 执行器统一创建 context
- **WHEN** 主采集任务启动（顺序或并行模式）
- **THEN** 浏览器进程由上层（如 collection router）启动（launch），仅将 browser 实例与任务参数传入执行器
- **AND** 执行器内部**统一**负责创建带指纹与可选会话的 browser context（`new_context(指纹, storage_state?)`），并在此 context 内完成登录与采集；顺序模式与并行模式均不依赖上层预先创建的 context，避免两套 context 逻辑并存

#### Scenario: 会话持久化
- **WHEN** 主采集执行器在本轮任务中成功完成登录流程（包括复用会话失效后回退到完整登录）
- **THEN** 浏览器会话状态按账号保存（data/sessions/[platform]/[account_id]/storage_state.json，通过 SessionManager，以带包装的 session_data 形式存储，其中的 `storage_state` 字段用于后续注入 Playwright context）以供重用
- **AND** 主采集执行器在下次同账号任务启动时优先加载该账号的会话（在有效期内），若存在且加载成功则从 session_data 中提取 storage_state 注入 context 并执行登录组件；若会话文件不存在、已过期或损坏导致加载失败，则视为无有效会话，回退到完整登录并在成功后保存新会话
- **AND** data/sessions 与 profiles 目录按安全规范管理（不进入 VCS、仅后端访问、权限控制）
- **AND** 运维与文档中须明确提醒「避免同一账号并发执行采集任务」，以防会话文件 load/save 竞态

#### Scenario: 复用会话无效时回退完整登录
- **WHEN** 主采集使用已加载的 storage_state 启动并执行登录组件，但站点侧会话已失效（如已登出、重定向回登录页或出现安全验证页）
- **THEN** 登录组件检测到未处于已登录状态后，执行完整登录流程
- **AND** 登录成功后通过 SessionManager.save_session 覆盖该账号的会话，避免旧会话残留导致后续任务反复失败

#### Scenario: 登录组件契约与落地范围
- **WHEN** 执行器在复用会话场景下调用登录组件（传入 config['reused_session']=True）
- **THEN** 各平台登录组件（当前主采集为 shopee、tiktok、miaoshou）按统一契约实现：先做已登录检测（如 URL/元素判断已在工作台），已登录则跳过并返回 success=True，未登录或需安全验证则执行完整登录并返回相应 success
- **AND** 执行器仅依赖该契约决定是否触发完整登录与 save_session，不关心平台具体实现细节；新平台接入时需实现同一契约并纳入验收；验收时须逐平台验证「已登录则跳过」行为真实生效，避免行为仍等价于每次都完整登录

### Requirement: 文件注册和元数据索引
系统 SHALL 自动将采集的文件注册到catalog_files表，并包含完整的元数据。

#### Scenario: 文件元数据提取
- **WHEN** 从平台下载新的Excel文件
- **THEN** 系统提取platform_code、shop_id、data_domain、granularity、date_range和file_hash，然后将记录插入catalog_files表
- **AND** 系统验证文件元数据完整性（platform_code, shop_id, data_domain, granularity, date_range不为NULL）
- **AND** 系统验证文件路径（file_path）正确且文件存在

#### Scenario: 重复文件检测
- **WHEN** catalog_files表中已存在相同file_hash的文件
- **THEN** 系统跳过注册并将文件标记为重复
- **AND** 系统记录重复文件信息到日志

#### Scenario: 文件注册验证
- **WHEN** 文件注册完成后
- **THEN** 系统验证文件记录已正确插入catalog_files表
- **AND** 系统验证文件状态为pending（待处理）
- **AND** 系统验证文件元数据字段完整且正确

### Requirement: 账号配置管理
系统 SHALL 支持通过local_accounts.py进行账号配置，包含login_url字段。

#### Scenario: 账号登录URL使用
- **WHEN** 采集器为平台账号初始化
- **THEN** 系统从账号配置中读取login_url并将其作为身份验证的唯一入口点

#### Scenario: 账号配置验证
- **WHEN** 账号配置缺少login_url字段
- **THEN** 系统抛出错误并提示用户添加login_url到配置中

### Requirement: 数据域支持
系统 SHALL 支持采集多个数据域：订单、产品、库存、流量、服务、分析和财务。

#### Scenario: 订单数据采集
- **WHEN** 用户选择订单数据域进行采集
- **THEN** 系统导航到订单导出页面并下载订单数据文件

#### Scenario: 产品数据采集
- **WHEN** 用户选择产品数据域
- **THEN** 系统导航到产品管理页面并导出产品列表数据

#### Scenario: 库存数据采集
- **WHEN** 用户选择库存数据域
- **THEN** 系统导出当前库存水平和库存变动

### Requirement: 采集状态监控
系统 SHALL 提供数据采集操作的实时状态监控。

#### Scenario: 采集进度跟踪
- **WHEN** 采集操作正在进行中
- **THEN** 系统更新采集状态并通过API端点提供进度信息

#### Scenario: 采集错误处理
- **WHEN** 由于网络错误或身份验证失败导致采集失败
- **THEN** 系统记录错误详情，保存错误截图，并向用户报告失败状态

### Requirement: 文件扫描和自动注册
系统 SHALL 支持扫描文件目录并自动注册新文件到catalog_files表。

#### Scenario: 文件目录扫描
- **WHEN** 用户调用文件扫描API或服务
- **THEN** 系统扫描指定目录（如data/raw/）查找Excel文件
- **AND** 系统识别文件元数据（从文件名或文件内容提取）
- **AND** 系统验证文件格式正确（Excel格式）

#### Scenario: 文件自动注册
- **WHEN** 扫描发现新文件
- **THEN** 系统自动注册文件到catalog_files表
- **AND** 系统提取文件元数据（platform_code, shop_id, data_domain, granularity, date_range）
- **AND** 系统计算文件哈希（file_hash）用于去重

#### Scenario: 文件扫描去重
- **WHEN** 扫描发现已存在的文件（file_hash相同）
- **THEN** 系统跳过注册，不创建重复记录
- **AND** 系统记录跳过信息到扫描结果

#### Scenario: 文件扫描结果统计
- **WHEN** 文件扫描完成
- **THEN** 系统返回扫描结果统计（seen, registered, skipped）
- **AND** 系统记录新注册的文件ID列表

### Requirement: 文件注册验证
系统 SHALL 提供文件注册验证功能，确保文件正确注册到catalog_files表。

#### Scenario: 文件注册完整性验证
- **WHEN** 验证文件注册时
- **THEN** 系统验证文件记录存在于catalog_files表
- **AND** 系统验证文件元数据字段完整（platform_code, shop_id, data_domain, granularity, date_range）
- **AND** 系统验证文件路径（file_path）正确且文件存在

#### Scenario: 文件元数据正确性验证
- **WHEN** 验证文件元数据时
- **THEN** 系统验证platform_code在允许的平台列表中
- **AND** 系统验证data_domain在允许的数据域列表中
- **AND** 系统验证granularity在允许的粒度列表中
- **AND** 系统验证date_range格式正确（如果存在）

#### Scenario: 文件注册状态验证
- **WHEN** 验证文件注册状态时
- **THEN** 系统验证新文件状态为pending（待处理）
- **AND** 系统验证文件哈希（file_hash）唯一性
- **AND** 系统验证文件创建时间（created_at）正确

### Requirement: 智能登录状态检测

系统 SHALL 在录制非 login 组件或执行数据采集任务前，智能检测当前浏览器会话是否已登录，避免不必要的重复登录。

#### Scenario: 持久化会话已登录检测

- **WHEN** 用户使用持久化会话录制非 login 组件（如 date_picker、navigation、export 等）
- **THEN** 系统导航到目标页面后，检测当前登录状态
- **AND** 如果检测到已登录（置信度 >= 70%），系统跳过登录组件执行，直接开始录制
- **AND** 系统记录"已检测到登录状态，跳过登录步骤"日志

#### Scenario: 持久化会话未登录检测

- **WHEN** 用户使用持久化会话录制非 login 组件，但会话未登录或已过期
- **THEN** 系统检测到未登录状态
- **AND** 系统自动加载并执行对应平台的 login 组件
- **AND** 登录成功后继续执行录制

#### Scenario: 登录状态检测综合判断

- **WHEN** 系统执行登录状态检测
- **THEN** 系统依次执行以下检测方法：
  - URL 检测：检查当前 URL 是否匹配已登录页面特征
  - 元素检测：检查页面是否存在已登录状态的 UI 元素
  - Cookie 检测：检查是否存在有效的认证 Cookie
- **AND** 系统综合三种检测结果，计算最终登录状态和置信度

#### Scenario: 等待自动跳转检测

- **WHEN** 系统导航到登录页面 URL（如包含 redirect 参数的 URL）
- **THEN** 系统等待最多 5 秒，检测 URL 是否自动跳转到已登录页面
- **AND** 如果检测到自动跳转，系统判断为已登录状态

#### Scenario: 检测失败降级处理

- **WHEN** 登录状态检测过程中发生异常
- **THEN** 系统记录异常信息
- **AND** 系统降级执行登录组件（保守策略，确保登录状态）

### Requirement: 登录检测日志记录

系统 SHALL 提供详细的登录检测日志，便于调试和问题排查。

#### Scenario: 检测过程日志记录

- **WHEN** 系统执行登录状态检测
- **THEN** 系统记录以下信息：
  - 导航的目标 URL
  - URL 检测结果和匹配的关键词
  - 元素检测结果和匹配的选择器
  - Cookie 检测结果和检测到的 Cookie
  - 最终判断结果和置信度
  - 检测耗时

#### Scenario: 调试模式详细日志

- **WHEN** 环境变量 `DEBUG_LOGIN_DETECTION=true` 被设置
- **THEN** 系统输出更详细的调试信息
- **AND** 检测失败时自动保存页面截图到 `temp/debug/login_detection/` 目录

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

### Requirement: 代理能力预留
系统 SHALL 在账号配置与浏览器上下文创建路径预留代理（proxy）相关接口；主采集执行器创建 context 时暂不注入 proxy，当前采集在住宅 IP 环境下无需启用代理。

#### Scenario: 代理预留不改变当前行为
- **WHEN** 主采集执行器创建浏览器上下文
- **THEN** 当前不向 context 注入 proxy，网络出口行为与变更前一致
- **AND** 配置或代码中保留 proxy_required、proxy 等字段的读取与传递，若未来需要多 IP/代理时可在此扩展并注入 context 的 proxy

### Requirement: 采集脚本编写规范

系统及贡献者在编写或修改数据采集相关的 Python 组件（如 `modules/platforms/*/components/*.py` 中的登录、导航、导出组件）时 SHALL 遵循项目《采集脚本编写规范》文档中的约定，以与 Playwright 官方最佳实践及业界主流设计保持一致，提升脚本稳定性与可维护性。规范文档至少涵盖：元素定位（优先 get_by_role / get_by_label / get_by_text，选择器集中至 *_config）；元素检测与可重试等待（禁止单次 count()+is_visible() 后即操作，应使用 expect(locator).to_be_visible() 或 locator.wait_for(state="visible") 或直接对 locator 执行 click/hover/fill）；等待策略（优先条件等待，慎用固定 wait_for_timeout）；复杂交互（悬停→内容出现→点击：trigger.hover() → 对菜单 wait_for(state="visible")，菜单项优先 get_by_role("menuitem", name="...")，再 hover/click，优先 locator 方法）；临时弹窗与遮挡层（执行器在登录前、每域导出前调用 close_popups，组件内已知弹窗显式 wait 再关闭/确认，不可预期弹窗可依赖执行器或 add_locator_handler）；各场景下如何编写脚本（场景与业界设计：临时验证码 OTP/图形含导出阶段同套流程、临时弹窗、临时遮罩、Toast、会话过期含每域前后检查、加载中、长时间生成/异步导出、下载确认含新标签页与下载路径约定、不可预期遮挡含 add_locator_handler 仅自包含 click 防死循环，以及 iframe 内操作、新标签页、平台限流、页面崩溃/超时的检测与应对及本项目编写要点）；组件契约（ExecutionContext、ResultBase 子类，脚本假定 context 已设置 accept_downloads 与 downloads_path）；错误与重试约定（含平台限流退避、page/context 关闭或超时时的策略）；多语言/多站点与 iframe 内定位约定；**iframe 与交互框/信息框类型**及各类业界检测与应对（罗列主流类型：同源业务/组件 iframe、跨域登录/支付/广告 iframe、Modal/Dialog、Drawer、Popover/Dropdown，及业界检测方式、应对方式按类型表格）；**现代化网页补充场景**（按业界主流写明检测与应对）：Shadow DOM（注明 locator 默认穿透）、动态列表/Stale（每次再查或唯一 key）、SPA 路由/导航（等目标页特征）、虚拟列表/无限滚动（滚动后 wait_for）、文件上传 set_input_files、Cookie 接受/拒绝显式 wait、空状态/无数据判断非空再操作、浏览器权限弹窗、多步向导每步后 wait、网络/请求失败与超时区分、**分页（Pagination）**（点击下一页后等当前页内容或列表刷新再继续）；规范可注明**以 Playwright Python 当前文档与 API 为准**；错误与重试含网络/请求失败时的策略。

#### Scenario: 新增或修改组件时遵循规范文档

- **WHEN** 开发者新增或修改采集用 Python 组件（登录、导航、导出等）
- **THEN** 元素定位优先使用 `page.get_by_role()`、`page.get_by_label()`、`page.get_by_text()`，或将易变选择器集中在平台 `*_config.py` 中
- **AND** 元素检测不依赖单次 `count() + is_visible()`；使用 `expect(locator).to_be_visible()` 或 `locator.wait_for(state="visible")` 或直接对 locator 执行 click/hover/fill
- **AND** 等待逻辑优先使用 Playwright 自动等待或显式条件等待，仅在确需人为节奏时使用 `wait_for_timeout` 并注明原因
- **AND** 组件符合现有契约（如 `LoginComponent.run(page)`、`ExportComponent.run(page, mode)`），返回统一的 `ResultBase` 子类

#### Scenario: 复杂交互（悬停→内容出现→点击）遵循规范

- **WHEN** 脚本需模拟「鼠标移至某处→点击或悬停后出现内容→再移到内容上点击」（如下拉菜单、级联菜单）
- **THEN** 对触发元素使用 `locator.hover()` 或 `locator.click()`，对出现的下拉/菜单使用 `menu_locator.wait_for(state="visible")` 或 `expect(menu_locator).to_be_visible()` 等待出现，不以固定 `wait_for_timeout` 替代
- **AND** 菜单项优先使用 `get_by_role("menuitem", name="...")` 或 `get_by_text()` 等稳定定位，再视需 `scroll_into_view_if_needed()`、`item.hover()` 后 `item.click()`；`page.mouse.move()`/`down()`/`up()` 仅作兜底

#### Scenario: 临时弹窗与遮挡层的处理约定

- **WHEN** 采集脚本运行过程中出现临时弹窗、通知或遮挡层
- **THEN** 规范文档说明执行器在登录前、每个数据域导出前会调用通用弹窗处理（close_popups），使用通用与平台配置（如 popup_config.yaml）的选择器及 ESC 进行关闭
- **AND** 组件内若已知某步会弹出对话框（如「确定」「导出」），应在流程中显式 wait 到该对话框可见再点击关闭或确认，不依赖固定延时
- **AND** 若弹窗出现时机不可预期，可依赖执行器在步骤边界的关闭，或文档中说明可选用 page.add_locator_handler 及注意事项

#### Scenario: 各场景下按规范编写脚本

- **WHEN** 脚本涉及验证码、弹窗、遮罩、Toast、会话过期、加载中、下载确认或不可预期遮挡等场景
- **THEN** 规范文档列出上述场景，并说明每种场景下业界主流的检测方式与应对方式
- **AND** 规范文档说明本项目中对应编写要点（与验证码提案、popup_handler、组件契约一致），供开发者按场景选用

#### Scenario: iframe 与交互框类型及业界检测/应对

- **WHEN** 脚本需在 iframe 内操作或与 Modal/Drawer/Popover 等交互框交互
- **THEN** 规范文档罗列主流 iframe 与交互框/信息框类型（同源业务与组件 iframe、跨域 iframe、Modal/Dialog、Drawer、Popover/Dropdown）及同源/跨域等属性
- **AND** 规范文档说明各类的业界检测方式（如 page.frames、frame_locator、主文档优先再 fallback iframe）与应对方式（同源 frame 内 locator/click、跨域仅检测与暂停回传、Modal 先 wait 再 get_by_role 等），便于编写者按类型选用

#### Scenario: 现代化网页补充场景与应对

- **WHEN** 脚本在现代化网页上运行（Shadow DOM、SPA 路由、虚拟列表/无限滚动、文件上传、Cookie 接受/拒绝、空状态、权限弹窗、多步向导、网络/请求失败、分页等）
- **THEN** 规范文档按业界主流写明上述场景的检测与应对：Shadow DOM 注明默认穿透、SPA 导航后等目标页特征、虚拟列表滚动后对目标 wait_for、文件上传用 set_input_files、Cookie 合规选择时显式 wait 接受/拒绝、空状态先判断非空再操作、权限弹窗与多步向导约定、网络/请求失败与页面超时区分、**分页**（点击下一页后等当前页内容或列表刷新再继续，不用固定 sleep）；规范可注明**以 Playwright Python 当前文档与 API 为准**
- **AND** 规范文档与提案「场景列表」「检测与应对概要」「现状与业界对照」中现代化网页补充行一致

#### Scenario: 真实采集环境下的场景与应对

- **WHEN** 脚本在真实采集环境中运行（iframe 内操作、新标签页弹出、长时间生成、平台限流、页面崩溃或导航超时、多语言/多站点、每域前后会话、导出阶段验证码等）
- **THEN** 规范文档涵盖 iframe 内定位与关闭弹窗、新标签页 expect_event("page") 与 close、下载路径约定、长时间生成条件等待、平台限流检测与退避、页面崩溃/超时与错误类型、多语言/多站点文案、每域前后会话检查、导出阶段验证码与登录同套流程等编写要点
- **AND** 规范文档与提案「现状与业界对照」表一致，使编写者按业界主流方式落笔

#### Scenario: 规范文档可被查阅

- **WHEN** 开发者或 Agent 需要编写或审查采集脚本
- **THEN** 项目文档索引（如 CLAUDE.md 或 docs/DEVELOPMENT_RULES/README.md）中提供对《采集脚本编写规范》的引用
- **AND** 规范文档位于约定路径（如 `docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md` 或与团队约定的 `docs/DEVELOPMENT_RULES/`），便于发现与维护

