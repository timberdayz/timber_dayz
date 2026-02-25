## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: 代理能力预留
系统 SHALL 在账号配置与浏览器上下文创建路径预留代理（proxy）相关接口；主采集执行器创建 context 时暂不注入 proxy，当前采集在住宅 IP 环境下无需启用代理。

#### Scenario: 代理预留不改变当前行为
- **WHEN** 主采集执行器创建浏览器上下文
- **THEN** 当前不向 context 注入 proxy，网络出口行为与变更前一致
- **AND** 配置或代码中保留 proxy_required、proxy 等字段的读取与传递，若未来需要多 IP/代理时可在此扩展并注入 context 的 proxy
