# Tasks: 采集持久化会话与按账号指纹对齐业界设计

## 1. 主采集接入按账号持久化会话

- [ ] 1.0 统一约定：以 CollectionExecutorV2.execute/execute_parallel_domains 的入参 `account_id` 为事实标准，进入执行器后立即将其规范为字符串（如 `str(account_id)`），并要求 account 配置中的 `account_id` 与之保持一致；当两者不一致或 account/配置中缺失 account_id 时，记录告警日志并在本次任务中**不尝试会话复用与按账号指纹**，回退到完整登录 + 全局指纹行为，避免同一逻辑账号对应到不同会话/指纹路径
- [ ] 1.1 执行器在启动采集任务时，按规范化后的 platform + account_id 调用 SessionManager.load_session（或等价接口），若在有效期内则取得 session_data 并从中提取 `session_data["storage_state"]` 用于注入；SessionManager 为同步 IO，在 async 执行器内须用 run_in_executor 调用或为 SessionManager 提供 async 封装，避免阻塞事件循环；若会话文件不存在、已过期或读取/解析失败，须记录日志并视为无可用会话，直接走完整登录
- [ ] 1.2 创建 browser context 时，若有有效 storage_state 则传入 new_context(storage_state=...)，再执行登录组件。执行器在调用登录组件时通过 config 或 params 传入「本次为复用会话」的标记（如 config['reused_session']=True），登录组件据此先做已登录检测（如是否已在后台工作台页）再决定跳过或执行完整登录；在「复用会话」场景下约定登录组件的返回值或异常语义（如返回 success=False 或抛出约定异常表示需完整登录），供执行器据此触发完整登录并在成功后保存新会话。**登录组件契约**：文档化「复用会话时：先检测已登录状态，已登录则跳过并返回 success=True，未登录或需安全验证则执行完整登录并返回 success=True/False」；当前主采集平台为 shopee、tiktok、miaoshou，各平台登录组件均需实现上述契约，可在验收时按平台标注优先级（主流量平台优先验收）
- [ ] 1.3 仅在本轮任务中**成功完成登录流程**时（包括复用会话失效后回退到完整登录），才将当前 context 的 storage_state 通过 SessionManager.save_session 保存到该账号路径；若复用会话后检测到无效则走完整登录并**覆盖**保存，避免旧会话或损坏会话残留；任务失败但未完成成功登录时不得覆盖已有会话文件
- [ ] 1.4 会话过期策略与 SessionManager 一致（如 max_age_days=30）；过期则走完整登录并重新保存
- [ ] 1.5 顺序执行与并行执行（execute / execute_parallel_domains）两种模式均需支持：启动时尝试 load_session 并注入、登录成功后 save_session、复用失败时回退完整登录并覆盖保存；**执行器统一建 context**：两种模式下均由执行器内部创建带指纹与可选会话的 context（不依赖上层预先创建的 context）
- [ ] 1.6 **Context 创建责任与调用方**：推荐 collection router 仅 `browser = await launch(...)` 并将 `browser` 传入执行器（顺序模式 `execute(browser=browser, ...)`，并行模式已为 `execute_parallel_domains(browser=browser, ...)`）；若顺序模式暂时保留传 `page`，则执行器从 `page.context.browser` 取得 browser 后自建 context 与 page，后续**仅使用自建 context**，传入的 page 取完 browser 后关闭，避免两套 context 并存。**实现必须满足**：顺序模式下执行器不得依赖 router 预先创建的 context 完成登录与采集，否则视为未达标
- [ ] 1.7 文档约定：会话存储事实标准路径为 data/sessions（SessionManager）；data/sessions 与 profiles 目录按安全规范管理（不进入 VCS、仅后端访问、权限控制）

## 2. 主采集按账号使用固定指纹

- [ ] 2.1 执行器创建 browser context 时，**统一**按 platform + 规范化后的 account_id（与 1.0 约定一致）从 **DeviceFingerprintManager** 获取/生成该账号的指纹（user_agent、viewport、locale、timezone_id 等），不混用 config/browser_fingerprints.py；顺序与并行两种模式均使用按账号指纹。若 DeviceFingerprintManager 的调用为同步 IO，则在执行器内用 run_in_executor 或 async 封装调用，与 SessionManager 一致，避免阻塞事件循环；当账号缺少有效 account_id 时，不尝试按账号指纹，记录告警并回退到当前全局指纹行为
- [ ] 2.2 将上述指纹参数注入 new_context(...)，替代当前仅使用 browser_config_helper 的全局固定参数，并校验 DeviceFingerprintManager 返回的上下文参数（如 permissions 字段）与 Playwright new_context API 的兼容性，必要时做适配转换

## 3. 代理接口预留

- [ ] 3.1 在账号配置与执行器/浏览器配置层保留 proxy 相关字段的读取与传递（如 proxy_required、proxy）；执行器创建 context 时暂不注入 proxy，保持当前出口行为不变
- [ ] 3.2 在代码或配置文档中注明：代理为预留能力，当前采集在住宅 IP 下无需启用；若未来需要多 IP/代理，可在此处启用并传入 context 的 proxy

## 4. 登录组件落地与契约

- [ ] 4.0 在文档中明确「登录组件统一契约」：复用会话时接收 `config['reused_session']=True`，先做已登录检测（如 URL/元素判断已在工作台），已登录则跳过并返回 success=True，未登录或需安全验证则执行完整登录并返回相应 success；执行器据此决定是否触发完整登录与 save_session
- [ ] 4.1 当前主采集平台（shopee、tiktok、miaoshou）的登录组件均需实现上述契约；实现时按平台逐项适配「已登录检测 + 完整登录回退」，验收时可标注主流量平台优先
- [ ] 4.2 **登录组件实现完备度验收**：逐平台验证「复用会话时先判已登录 → 已登录则跳过并返回 success，未登录则执行完整登录」的行为真实生效（例如通过日志、二次任务无需再输入密码或检测到已在工作台页），避免规范正确但行为仍等价于每次都完整登录

## 5. 验收与文档

- [ ] 5.1 验收：同一账号连续两次采集任务，第二次在会话有效期内可复用会话（登录组件检测到已登录则跳过，或无需再次输入账号密码即可进入导出流程）
- [ ] 5.2 验收：复用会话后若站点已登出，登录组件检测到未登录则走完整登录并覆盖保存，任务可正常完成
- [ ] 5.3 验收：不同账号使用不同指纹（如 UA/viewport 按账号区分），主采集 context 参数来自 DeviceFingerprintManager
- [ ] 5.4 在数据采集或运维文档中补充「按账号持久化会话、会话有效性检测与回退、按账号指纹（DeviceFingerprintManager）、data/sessions 存储与安全、代理预留、执行器统一建 context、登录组件契约与落地范围（shopee/tiktok/miaoshou）」说明，并**明确提醒**：避免同一账号并发执行采集任务，以防会话文件 load/save 竞态
- [ ] 5.5 验收：人为删除或损坏某账号的会话文件后，再次启动任务能够自动回退到完整登录并重新保存有效会话，不会出现无限重试或死循环
- [ ] 5.6 验收：同一账号在顺序模式（execute）与并行模式（execute_parallel_domains）下，会话复用与按账号指纹行为一致（包括是否尝试复用、何时回退完整登录、最终保存的会话与指纹来源一致）
- [ ] 5.7 验收：顺序模式下执行器使用的 context 为执行器自建（带指纹与可选会话），而非上层预先创建的全局 context；可通过日志或行为验证 context 来源一致
