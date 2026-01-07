## MODIFIED Requirements

### Requirement: 多平台数据采集

系统 SHALL 支持从多个电商平台（包括 Shopee、TikTok、Amazon 和妙手 ERP）进行自动化数据采集，并提供可靠的登录状态检测机制。

#### Scenario: Shopee 订单数据采集

- **WHEN** 用户使用有效的账号凭证启动 Shopee 平台采集
- **THEN** 系统使用 Playwright 自动化浏览器，登录 Shopee 卖家中心，导航到订单导出页面，下载 Excel 文件，并将文件元数据注册到 catalog_files 表
- **AND** 系统记录采集任务的执行时间和状态

#### Scenario: TikTok 产品数据采集

- **WHEN** 用户启动 TikTok Shop 平台采集
- **THEN** 系统自动化浏览器会话，使用 TikTok 凭证进行身份验证，导出产品数据，并将文件保存到 downloads 目录

#### Scenario: 跨平台采集会话持久化

- **WHEN** 采集会话被中断或浏览器关闭
- **THEN** 系统将会话状态保存在会话文件中，可以在不重新认证的情况下恢复采集

## ADDED Requirements

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
