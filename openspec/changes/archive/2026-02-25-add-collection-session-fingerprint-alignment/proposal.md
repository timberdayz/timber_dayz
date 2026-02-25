# Change: 采集持久化会话与按账号指纹对齐业界设计

## Why

1. **主采集未接入已有持久化与指纹设计**：系统已具备按账号的会话持久化（SessionManager：`data/sessions/<platform>/<account_id>/storage_state.json`、`profiles/<platform>/<account_id>/`）与按账号固定指纹（DeviceFingerprintManager、config/browser_fingerprints.py），但主采集执行器（executor_v2）未使用——每次任务重新登录、浏览器上下文使用全局固定 UA/viewport，与 data-collection spec 中「会话保存到 profiles 以供重用」「应用浏览器指纹配置」及业界「每账号固定指纹、复用会话减少验证码」做法不一致。
2. **与业界主流对齐**：业界常见做法为每账号独立 profile 或 storage_state 持久化、下次同账号复用以降低登录与验证码频率；每账号固定指纹避免多账号同指纹或随机指纹带来的风控。需在主采集路径接入上述能力。
3. **代理预留、暂不启用**：当前采集在个人住宅 IP 环境下运行，暂不需要代理；预留代理接口（配置项与执行器入参），未来若需多 IP/代理时可更新即用。

## What Changes

- **主采集接入按账号持久化会话**：执行器在**完成本轮成功登录流程后**（包括复用会话失效后回退到完整登录），将本次任务的浏览器状态 `storage_state` 通过 SessionManager 保存到该账号对应路径（`data/sessions/<platform>/<account_id>/storage_state.json`，文件内容为带包装的 session_data，实际注入 Playwright 时仅使用其中的 `session_data["storage_state"]` 字段）；在启动采集任务时，优先尝试从 SessionManager 按 `platform + account_id` 加载该账号的会话（在有效期内），若加载成功则从返回的 session_data 中提取 `storage_state` 并注入 `browser.new_context(storage_state=...)` 再执行登录组件；若会话文件不存在、已过期或损坏导致加载失败，则视为无可用会话，直接走完整登录流程并在成功后保存新会话。**会话有效性**：登录组件在复用会话后须检测「是否仍处于已登录状态」（如已进入目标控制台/工作台，而非登录页或安全验证页）；若检测到已登出、重定向回登录页或需安全验证，则回退到完整登录流程并再次调用 SessionManager.save_session 覆盖旧会话，避免卡在半有效状态或被损坏会话反复卡死。会话过期策略沿用现有 max_age_days（如 30 天），与 SessionManager 一致。**存储与安全**：data/sessions 与 profiles 目录按现有安全规范管理（不进入 VCS、仅后端节点访问、权限控制），文档中说明会话文件仅限采集服务使用。
- **主采集按账号使用固定指纹**：执行器创建浏览器上下文时，**统一**按 `platform + account_id`（以执行器入参 `account_id` 为事实标准，并与 account 配置中的 account_id 字段保持一致，必要时在进入执行器前做字符串规范化）从 **DeviceFingerprintManager** 获取或生成该账号的指纹（user_agent、viewport、locale、timezone_id 等），注入 `new_context(...)`，与录制、PersistentBrowserManager 等路径一致，实现「一账号一指纹」。主采集不混用 config/browser_fingerprints.py，避免两套指纹源导致同一账号在不同路径指纹不一致；若未来需迁移至 config 或统一入口，可在单独变更中收敛。若账号缺少有效的 account_id（为空或无法安全转换为字符串），则不尝试按账号指纹与会话复用，显式记录告警日志并回退到当前全局默认指纹/完整登录行为。
- **代理接口预留**：在账号配置与执行器/浏览器配置层保留 proxy 相关字段（如 `proxy_required`、`proxy` 的读取与传递）；执行器创建 context 时**暂不**注入 `proxy`，即当前行为不变。在文档或配置中注明「代理为预留能力，当前住宅 IP 无需启用；若未来需要可在此处启用并传入 context 的 proxy」；实现上可预留可选参数 `proxy: Optional[Dict]`，仅在明确启用时注入 context。
- **登录组件落地范围（业界对齐）**：按平台/站点拆分登录组件、契约统一、实现分平台。执行器只依赖统一契约（`config['reused_session']`、返回值 success、可选异常「需完整登录」）；各平台登录组件按同一契约实现「复用会话时先做已登录检测，通过则跳过，未通过则执行完整登录」。**落地范围**：所有被主采集使用的平台的登录组件均需实现上述复用会话场景的已登录检测与完整登录回退；当前主采集支持的平台为 shopee、tiktok、miaoshou，可在 tasks 中逐平台验收或标注优先级（主流量平台优先，其余平台可暂在复用会话时走完整登录再逐步补齐）。
- **执行器统一建 context（业界对齐）**：由「执行会话的单元」即执行器负责创建并持有 browser context，上层（如 collection router）只负责启动 browser 进程（`launch`）并将 `browser` 与任务参数（platform、account_id、account 等）交给执行器。**推荐实现**：Router 仅调用 `browser = await playwright.chromium.launch(...)`，不创建 context；顺序模式与并行模式均将 `browser` 传入执行器（`execute(browser=browser, ...)` / `execute_parallel_domains(browser=browser, ...)`），执行器内部按 platform + account_id 获取指纹与可选会话，再 `context = await browser.new_context(指纹, storage_state?)` 并 `page = await context.new_page()`，后续登录与采集均在此 context 内完成。**兼容方案**：若顺序模式暂时仍需保留传入 `page` 的接口，则执行器在入口处用 `page.context.browser` 取得 browser，自行 `new_context(指纹, storage_state?)` 并 new_page，后续只使用执行器自建的 context/page，传入的 page 仅用于取 browser 后即关闭，避免两套 context 逻辑并存。并行模式下执行器先建登录用 context 完成登录并取得 storage_state，再为各域 `new_context(storage_state=..., 指纹)`，与当前设计一致。

## Impact

- **Affected specs**: data-collection（MODIFIED：会话持久化与浏览器指纹管理在主采集路径的落地方式；ADDED：代理预留说明）
- **Affected code**:
  - `modules/apps/collection_center/executor_v2.py`：启动任务时在顺序与并行两种模式下统一按 `platform + account_id` 尝试 SessionManager.load_session，若加载成功则从 session_data 中提取 `storage_state` 并注入 context，加载失败则回退完整登录；**由执行器统一创建**带指纹与可选会话的 browser context（见上文「执行器统一建 context」），顺序模式接收 browser 或兼容从传入 page 取 browser 后自建 context；创建 context 时**统一**使用 DeviceFingerprintManager 按账号指纹（从执行器入参统一获取并规范化 account_id），同时在登录组件配置中传入 `reused_session` 标记以驱动「已登录检测→必要时完整登录」流程；仅在本轮成功完成登录后调用 SessionManager.save_session（避免在任务失败但未成功登录时覆盖有效会话）；复用会话后依赖登录组件的「仍已登录」检测，失败则回退完整登录并覆盖保存；预留 proxy 参数（可选，默认不注入），并通过日志记录「是否复用会话、是否回退完整登录、是否成功保存会话」等关键信息，便于运维排查。
  - `backend/routers/collection.py`（或等价调用方）：顺序模式推荐改为仅 launch browser 并将 `browser` 传入 `execute(browser=browser, ...)`，不再预先创建 context/page；若采用兼容方案则保持传 page，由执行器内部取 browser 并自建 context。
  - `modules/apps/collection_center/browser_config_helper.py`：可选扩展为提供「按账号获取 context 参数」的入口，或由 executor 直接调用 DeviceFingerprintManager
  - 各平台登录组件（shopee、tiktok、miaoshou）：实现复用会话场景下的已登录检测与完整登录回退，遵守执行器与登录组件间的统一契约（见上文「登录组件落地范围」）。
  - 文档：数据采集或运维文档中说明「按账号持久化会话、会话有效性检测与回退、按账号指纹（DeviceFingerprintManager）、data/sessions 存储与安全、代理预留、执行器统一建 context、登录组件契约与落地范围」

## Non-Goals

- 代理当前不实现注入；仅预留配置与参数，不改变现有网络出口行为。
- 不在此变更中实现 PersistentBrowserManager 的 launch_persistent_context 替代 new_context（可选后续优化）；优先采用「new_context + storage_state 注入」以最小改动落地会话复用。
- 不在此变更中处理同一账号并发采集时的会话竞态（如两任务同时 load/save 同一账号）；若需支持，可后续通过任务排队或账号级锁处理。**运维约定**：文档与运维说明中须明确提醒「避免同一账号并发执行采集任务」，以防会话文件竞态。

## 实施与运维（可选）

- **回退开关**：实现时可按运维需要预留配置项（如关闭「按账号会话」或「按账号指纹」），使主采集回退为「每次完整登录 + 全局指纹」行为，便于上线后快速止血；非强制，由实现方决定是否加入。
