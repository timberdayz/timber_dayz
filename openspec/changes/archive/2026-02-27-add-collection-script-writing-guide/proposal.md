# Change: 真实采集脚本编写规范

## Why

1. **按业界主流方式编写采集脚本**：本变更交付《采集脚本编写规范》文档，作为**唯一成文依据**，使后续新增与修改采集脚本可**按业界主流方式**编写（Playwright 官方推荐 + 各打断类场景的通用检测与应对），提升稳定性、可维护性并与行业实践对齐。
2. **与 Playwright 官方及业界一致**：当前采集组件中大量使用 `page.locator("button:has-text(...)")`、`page.locator(".class")` 等易变选择器，以及固定 `wait_for_timeout`。Playwright 官方推荐优先使用 `get_by_role` / `get_by_label` / `get_by_text` 和条件等待。
3. **元素检测不足**：脚本中普遍使用「单次」`loc.count() > 0 and await loc.first.is_visible()` 再操作，不重试，页面稍慢或动画未结束即失败。官方要求用可重试的 `expect(locator).to_be_visible()` 或 `locator.wait_for(state="visible")`，或直接对 locator 执行 click/hover 以利用 auto-wait。
4. **复杂交互缺少统一约定**：悬停→出现内容→再移到内容上点击（如下拉菜单、级联菜单）的流程需与官方一致：trigger.hover() → 对下拉/菜单条件等待可见 → 菜单项用 get_by_role('menuitem', name='...') 等稳定定位 → hover（如需）→ click；慎用固定 timeout，优先 `wait_for(state="visible")`。
5. **各场景检测与应对未成文**：验证码、弹窗、遮罩、Toast、会话过期、加载、下载、不可预期遮挡等场景，项目已有部分实现（如执行器 close_popups、验证码暂停回传、expect_download），但组件内写法与业界主流的差距（如 get_by_*、可重试等待、显式 wait 再点）无集中说明，规范文档将补齐缺口并统一为业界主流写法。
6. **渐进式改进**：通过规范文档 + 可选参考示例，在不破坏现有组件的前提下，为新增与修改脚本提供明确指引，便于后续逐步迁移旧代码。

## What Changes

**目标**：交付《采集脚本编写规范》后，**后续可完全按照业界主流方式编写采集脚本**——以该文档为唯一成文依据，涵盖定位、等待、契约与各场景的检测/应对，并与现有执行器、验证码提案、popup_handler 契约一致。

### 1. 新增采集脚本编写规范文档

- 在 `docs/guides/` 或 `docs/DEVELOPMENT_RULES/` 下新增**采集脚本编写规范**文档（如 `COLLECTION_SCRIPT_WRITING_GUIDE.md`）。
- 内容至少包含：
  - **元素定位**：优先使用 `page.get_by_role()`、`page.get_by_label()`、`page.get_by_text()`；避免依赖易变的 CSS 类、ID 或复杂 XPath；若必须使用 `locator(selector)`，将选择器集中在 `*_config.py` 并注明多语言/改版风险。**多语言/多站点**：按钮优先 `get_by_role`；若用文案则从配置读取多语言候选（如「确定」「OK」）或集中至 `*_config` 并注明语言/改版风险。**iframe 内元素**：操作前先用 `page.frame_locator("iframe").first` 或选定 `page.frames`，再在该 frame 上做 locator/wait/click；关闭弹窗时若弹窗在 iframe 内，需在对应 frame 上执行（与 popup_handler 遍历 frames 一致）。规范文档须单独列出**主流网页中 iframe 与交互框/信息框的类型**及**各类的业界检测与应对**（见下「iframe 与交互框类型与业界检测/应对」），便于按类型选用。**Shadow DOM**：若元素在 Shadow Root 内，Playwright 的 locator 默认穿透 shadow，规范注明此点即可，避免误判「无此元素」。**动态列表/Stale**：对虚拟列表或框架复用 DOM 的列表，优先每次按当前 DOM 再查（如用文本/role 再 locator）或使用带唯一 key 的 selector，避免长期持有可能被复用的 locator 导致点击错位。
  - **元素检测与可重试等待**：禁止仅用「单次」`loc.count() > 0 and await loc.first.is_visible()` 后即操作。应使用可重试方式之一：`expect(locator).to_be_visible()`（Python API）、`locator.wait_for(state="visible", timeout=...)`，或直接对 locator 执行 `click()`/`hover()`/`fill()`，依赖 Playwright 的 actionability 自动等待。需要「等某元素出现再继续」时用条件等待，不用固定 `wait_for_timeout` 替代。
  - **等待策略**：优先使用 Playwright 自动等待或显式条件等待（如 `expect(locator).to_be_visible()`、`locator.wait_for(state="visible")`）；仅在确需「人为节奏」时使用 `wait_for_timeout`，并注明原因。
  - **复杂交互（悬停→内容出现→点击）**：模拟真人操作时，推荐流程为：对触发元素 `locator.hover()` → 对下拉/菜单/弹出层使用 `menu_locator.wait_for(state="visible")` 或 `expect(menu_locator).to_be_visible()` 等待出现（勿用固定毫秒替代）→ 对菜单项优先 `get_by_role("menuitem", name="...")` 或 `get_by_text()` 等稳定定位 → 视需 `scroll_into_view_if_needed()`、`item.hover()` → `item.click()`。优先 locator 的 hover/click，`page.mouse.move()`/`down()`/`up()` 仅作兜底。
  - **组件契约**：与现有 `ExecutionContext`、`LoginComponent.run(page)`、`ExportComponent.run(page, mode)` 一致；配置从 `ctx.config` 与 `*_config` 读取，不写死选择器。脚本假定 **context 已设置 `accept_downloads=True` 且 `downloads_path` 为任务下载目录**；组件仅使用传入的 `download_dir`/`ctx.config` 内路径保存文件。
  - **错误与重试**：关键步骤配合 `RetryStrategy` 或组件内重试；返回统一 `ResultBase` 子类。遇**平台限流/429/「请稍后再试」**时检测页面限流文案或 HTTP 429，退避后重试（与现有 backoff 一致）。遇 **page/context 关闭或导航超时**时，视策略重试或快速失败并返回明确错误类型，便于上层区分可重试与不可重试。遇**网络离线/请求失败**（接口 5xx、超时、离线）时，按策略重试或快速失败并明确错误类型，与「页面超时」区分便于上层处理。
  - **临时弹窗与遮挡层**：说明执行器在**登录前、每个数据域导出前**会调用通用弹窗处理（`close_popups`），使用通用 + 平台配置（如 `config/collection_components/<platform>/popup_config.yaml`）的选择器与 ESC 关闭常见弹窗；组件内若**已知**某步会弹出对话框（如「确定」「导出」），应在流程中**显式** wait 到该对话框可见再点击关闭/确认；若弹窗出现时机不可预期，可依赖执行器在步骤边界的关闭，或说明可选用 Playwright 的 `page.add_locator_handler`（并注明会改变 focus/mouse 状态）。与业界「可预期弹窗显式关闭 + 执行器级兜底」一致。
  - **各场景下如何编写脚本（场景与业界设计）**：列出以下场景，对每种说明**业界主流的检测方式**与**应对方式**，以及**本项目中脚本应如何编写**（与验证码提案、popup_handler、现有组件契约对齐）：
    - 临时验证码（OTP、图形）：检测用 DOM/文案，有头/无头同一套；应对为暂停→人工或合规打码回传→同 page 填入继续；输入框用 get_by_role/get_by_placeholder，等可见再 fill。**导出阶段**若出现验证码，与登录阶段同一套：检测→VerificationRequiredError→暂停→回传→同 page 填入继续。
    - 临时弹窗（Cookie/公告/促销）：可预期则在流程中 wait 到关闭按钮可见再点击；不可预期依赖执行器 close_popups 或 add_locator_handler。若需**合规选择**（接受/拒绝 Cookie），显式 wait 到「全部接受」或「全部拒绝」按钮再点击，选择器可放平台 popup_config。
    - 临时遮罩（Modal/Dialog 业务确认）：操作后对预期对话框做 wait_for(visible)/expect，再 get_by_role("button", name="确定") 等点击；避免固定 wait_for_timeout。
    - 临时消息（Toast/Snackbar）：多不主动关；若挡点击可 wait_for(state="hidden") 或短等，慎用长 timeout。
    - 会话过期/重定向登录：关键步后检查 URL 或登录页/工作台特征；与现有「已登录则跳过、未登录则完整登录」契约一致。**每个数据域导出前或导出后**可检查是否被重定向到登录页，若掉线则重新登录后再继续下一域。
    - 加载中/骨架屏：以目标元素可见或 loading 消失为条件等待，或直接对目标元素操作；少用固定延时。**长时间生成/异步导出**：平台显示「生成中」「处理中」数分钟时才出现下载时，以该文案消失或「下载」按钮可见为条件等待（较长 timeout），不用固定长 sleep。
    - 下载确认/文件弹窗：在触发下载的 click 前先 context.expect_download()，再执行点击；若有确认框先 wait 到可见再点按钮。若导出会**打开新标签页**，应先 `page.context.expect_event("page")` 再点击，在新 page 上 wait/点击/等下载后 close 新 page。脚本假定 context 已设置 accept_downloads 与 downloads_path，仅使用任务目录保存。
    - 不可预期遮挡：执行器步骤边界轮询关闭；或 add_locator_handler，**handler 内仅做自包含 click 关闭**，避免复杂逻辑或再次触发同一 handler（防死循环）；并注明会改变 focus/mouse 状态。**浏览器权限弹窗**（通知/位置/麦克风等）可依赖执行器步骤边界关闭或 add_locator_handler；若需自动选允许/拒绝，可配置选择器。
- **现代化网页补充场景**（规范文档须按业界主流写明检测与应对）：
  - **SPA 路由/导航**：点击后仅前端路由切换、无整页 reload 时，先等**目标页特征元素**可见（或 URL 变化 + 特征）再继续，不用固定 sleep。
  - **虚拟列表/无限滚动**：列表仅渲染可见项、滚动才加载更多时，先滚动使目标进入视口或滚动到底触发加载，再对目标元素条件等待；或等「加载更多」消失后对目标 locator wait_for。
  - **文件上传（input file）**：导出/导入流程中「选择文件」用 `locator('input[type=file]').set_input_files(path)`，不通过 click 打开系统对话框；若有上传进度则按「加载中」或条件等待。
  - **空状态/无数据**：依赖「列表有数据」的流程前，先判断非空状态或等「有数据」特征，再执行导出/操作，避免对禁用或隐藏按钮操作。
  - **多步向导（Stepper/Wizard）**：每步操作后等「下一步」按钮或本步结果区域可见再继续，不用固定延时替代。
  - **分页（Pagination）**：点击「下一页」后等**当前页内容或列表刷新**再继续取数或操作，可归入加载中或条件等待，不用固定 sleep。
- **API 与版本**：规范文档可注明「以 Playwright Python **当前文档与 API** 为准」，避免 API 升级后 sync/async 或方法签名变更导致歧义。
- 可选：在文档中引用 Playwright 官方 Best Practices、Actionability、Locators 文档与项目内已符合规范的示例（如部分使用 `get_by_role` 的登录组件、妙手导出中的 getByRole menuitem）。

### 2. 场景列表与业界设计概要（供规范文档引用）

规范文档中「各场景下如何编写脚本」一节可包含如下场景列表与检测/应对概要表（业界主流 + 本项目约定）：

**场景列表**

| 场景类型 | 典型表现 | 常见触发时机 |
|----------|----------|----------------|
| 临时验证码（OTP） | 短信/邮箱验证码输入框、「验证码已发送」 | 登录/2FA |
| 临时验证码（图形） | 「请输入验证码」+ 图形/输入框 | 登录错误、风控或始终出现 |
| 临时弹窗（Cookie/公告/促销） | Cookie 同意条、公告/促销弹窗 | 首访、定时或随机 |
| 临时遮罩（Modal/Dialog） | 需点击「确定/关闭」的对话框 | 导出/删除等操作后 |
| 临时消息（Toast/Snackbar） | 顶部/底部短时提示 | 操作成功/失败反馈 |
| 会话过期/重定向登录 | 被重定向到登录页、出现登录表单 | 会话超时、多端登出 |
| 加载中/骨架屏 | loading 动画、骨架块、按钮 disabled | 页面/列表/接口未就绪 |
| 下载确认/文件弹窗 | 导出后「导出/确定/开始导出」等 | 导出流程中的二次确认 |
| 不可预期遮挡 | 任意时间出现的浮层、插播 | 难以用固定步骤描述 |
| iframe 内操作 | 按钮/表单在 iframe 内 | 导出、选择字段等 |
| 新标签页弹出 | 点击后打开新 tab，下载或确认在新页 | 部分平台导出流程 |
| 长时间生成/异步导出 | 「生成中」「处理中」数分钟后才可下载 | 报表/订单导出 |
| 平台限流/操作频繁 | 429、「请稍后再试」「操作过于频繁」 | 短时多次导出或操作过快 |
| 页面崩溃/导航超时 | page/context 关闭、导航超时 | 网络抖动、目标站异常 |
| Shadow DOM | 组件在 shadow root 内，普通选择器可能打不到 | 现代组件库、微前端 |
| SPA 路由/导航 | 点击后仅前端路由切换、无整页 reload | 单页应用内跳转 |
| 虚拟列表/无限滚动 | 仅渲染可见项，滚动才加载更多 DOM | 长列表、报表 |
| 文件上传（input file） | 「选择文件」触发上传或导入 | 导入、附件 |
| Cookie 接受/拒绝 | 需主动点「全部接受」或「全部拒绝」 | 合规、首访 |
| 空状态/无数据 | 列表无数据时按钮禁用或隐藏 | 导出前、筛选后 |
| 浏览器权限弹窗 | 通知/位置/麦克风等浏览器级弹窗 | 部分站点请求权限 |
| 多步向导（Stepper/Wizard） | 多步流程，每步「下一步」 | 导出/配置向导 |
| 网络/请求失败 | 接口 5xx、超时、离线 | 弱网、服务异常 |
| 分页（Pagination） | 点击下一页后列表/内容刷新 | 列表多页、报表分页 |

**检测与应对概要（业界主流）**

| 场景 | 检测方式（主流） | 应对方式（主流） |
|------|------------------|------------------|
| OTP / 图形验证码 | DOM/文案（输入框、提示）；有头/无头同一套 | 检测→暂停→人工或合规回填→同 page fill+click 继续 |
| Cookie/公告/促销弹窗 | 显式 wait 到关闭按钮可见，或 add_locator_handler/步骤前轮询 | 可预期：流程内 wait+点击；不可预期：handler 或步骤边界轮询 |
| 业务 Modal/Dialog | 操作后对预期 dialog 做 wait_for(visible)/expect | wait 到可见→get_by_role 点确定/取消 |
| Toast/Snackbar | 需断言时定位容器+wait 可见；防挡点击可 wait hidden | 多不主动关；必要时等消失或短等 |
| 会话过期 | URL/登录表单/成功页特征；关键步后或周期检查 | 重新登录或注入 storage_state，继续 |
| 加载中/骨架屏 | 等目标元素可见或 loading 元素 hidden | 对目标元素直接操作或显式 wait |
| 下载确认 | 先 expect_download 再 click；确认框 wait_for(visible) | 先注册 expect_download→点击→若有确认框 wait+点按钮 |
| 不可预期遮挡 | add_locator_handler 或步骤边界轮询 | handler 内自包含 click；或执行器轮询关闭 |
| iframe 内操作 | frame_locator 或选定 page.frames 后再定位 | 在选定 frame 上 locator/wait/click；弹窗在 iframe 内时在对应 frame 关闭 |
| 新标签页 | expect_event("page") 再点击，在新 page 操作后 close | 在新 page 上 wait/点击/等下载，然后 new_page.close() |
| 长时间生成 | 等「生成中」等文案消失或「下载」按钮出现 | 条件等待 + 较长 timeout；可配置 processing_indicators |
| 平台限流 | 检测限流文案或 429，退避重试 | 退避后重试；必要时步骤间短延时 |
| 页面崩溃/超时 | 重试或快速失败，明确错误类型 | RetryStrategy 或快速失败，区分可重试与不可重试 |
| Shadow DOM | Playwright locator 默认穿透 shadow | 规范注明默认穿透，避免误判无此元素 |
| SPA 路由/导航 | URL 或目标页特征元素 | 等目标页特征元素可见（或 URL+特征）再继续，不用固定 sleep |
| 虚拟列表/无限滚动 | 目标是否在 DOM、加载更多是否消失 | 先滚动使目标入视口或触底加载，再对目标 wait_for；或等加载更多消失后 wait_for 目标 |
| 文件上传 | input[type=file] 存在 | locator('input[type=file]').set_input_files(path)；有进度则按加载中/条件等待 |
| Cookie 接受/拒绝 | wait 到接受/拒绝按钮可见 | 显式 wait 再点击，选择器可配置 |
| 空状态/无数据 | 列表非空或「有数据」特征 | 先判断非空或等有数据特征，再执行导出/操作 |
| 浏览器权限弹窗 | 步骤边界或 handler 检测 | 执行器轮询关闭或 add_locator_handler；需自动选时配置选择器 |
| 多步向导 | 每步后下一步/结果区域 | 每步后 wait 下一步按钮或结果区域可见再继续 |
| 网络/请求失败 | 接口失败、超时、离线 | 重试或快速失败，明确错误类型，与页面超时区分 |
| 分页（Pagination） | 当前页内容或列表已刷新 | 点击下一页后等当前页内容或列表刷新再继续，不用固定 sleep |

**iframe 与交互框/信息框的类型与业界检测/应对**

规范文档中「iframe 内元素」或「各场景」一节可包含以下类型罗列与业界约定，供编写者按类型选用：

**主流 iframe 与交互框/信息框类型**

| 类型 | 典型表现 | 常见场景 | 同源/跨域 |
|------|----------|----------|-----------|
| 同源业务 iframe | 后台内嵌的报表、表单、字段选择 | 导出字段选择（如 iframe[title*='选择导出字段']）、列表/表格内嵌、筛选面板 | 同源 |
| 同源组件 iframe | 日期/时间选择、富文本、图表 | 日期控件在 iframe 内（如 EDS arco-picker）、部分 UI 库把复杂控件放在 iframe | 同源 |
| 跨域登录/认证 iframe | 第三方登录、OAuth、SSO 登录框 | 平台内嵌「用 XX 账号登录」 | 跨域 |
| 跨域支付/安全 iframe | 支付、验证码、人机验证 | reCAPTCHA、支付网关 | 跨域 |
| 跨域广告/统计 iframe | 广告、埋点、客服 | 广告位、客服浮窗 | 跨域 |
| Modal/Dialog（主文档） | 页内对话框+遮罩 | 确认框、导出进度、错误提示（.jx-dialog__body、.ant-modal、[role="dialog"]） | 主文档 |
| Drawer/侧边抽屉 | 从侧边滑出的面板 | 筛选、设置、详情 | 主文档或 iframe 内 |
| Popover/Dropdown（主文档或 iframe） | 气泡、下拉菜单 | 导出下拉「导出全部订单」、日期快捷项 | 主文档或 iframe 内 |

**业界检测方式（按类型）**

| 对象 | 检测方式 | 说明 |
|------|----------|------|
| 是否有 iframe | page.frames（可递归 child_frames） | 取 Frame 列表，再在目标 frame 上 frame.locator(...) |
| 用选择器锁定 iframe | page.frame_locator("iframe").first 或 iframe[title*=...] | 有 title/name 时更稳，选择器可配置（如 iframe_locators） |
| iframe 是否就绪 | 在 frame 内等 body 或关键元素 wait_for | 避免未加载完就操作；若 iframe 会刷新需轮询或短时重试 |
| Modal/Dialog（主文档） | page.locator('.ant-modal, .jx-dialog__body, [role="dialog"]').wait_for(state='visible') | 先等容器出现，再在主文档上 locator |
| Modal 内嵌 iframe | 先等主文档 dialog 可见，再 dialog.locator('iframe') 或 page.frame_locator('iframe') | 弹窗内容在 iframe 里时，在 frame 内定位按钮/表单 |
| 交互框在主文档还是 iframe | 主文档先试 page.get_by_role/page.locator；若无再遍历 page.frames 或 frame_locator | 与「Prefer dialog in main page; fallback to iframe」一致 |

**业界应对方式（按类型）**

| 类型 | 应对方式 | 注意点 |
|------|----------|--------|
| 同源业务 iframe | frame_locator(selector).first 或从 page.frames 选目标 frame，再 frame.locator(...).click()；选择器集中配置（如 iframe_locators + 内部按钮） | 优先用 iframe 的 title/name 做 selector；内部元素优先 get_by_role/get_by_text |
| 同源组件 iframe（如日期） | 递归 page + frames/child_frames 为 roots，在每个 root 上找面板容器（如 .arco-picker-dropdown），在该 root 上 click；或单一 iframe 时用 frame_locator("iframe").first | iframe 会刷新/延迟加载时需 wait_for 或短轮询 |
| 跨域 iframe | 能操作的：等 load 后在同一 context 内 frame_locator/frame 操作。受同源限制的：仅检测存在（如验证码 iframe），走暂停→人工/打码→回传，不跨域操作 DOM | 与验证码提案一致 |
| Modal/Dialog（主文档） | wait_for(visible) 到对话框容器，再 page 上 get_by_role("button", name="确定") 等点击 | 不用固定 timeout 替代等对话框出现 |
| Modal 内嵌 iframe | 先等主文档 dialog 可见；内容在 iframe 则 page.frame_locator('iframe').first 内勾选/点击导出，再回主文档点确定/关闭 | 与「先 dialog 再 iframe 兜底」一致 |
| Popover/Dropdown | 主文档：trigger hover/click → menu_locator.wait_for(visible) → get_by_role("menuitem", name="...")；在 iframe 内则先进入对应 frame 再同样流程 | 与复杂交互规范一致 |

**现状与业界对照（规范文档将补齐的缺口）**

规范文档撰写时，以下缺口须在「各场景下如何编写脚本」及对应小节中明确对齐方式，使编写者按业界主流落笔：

| 场景/维度 | 业界主流 | 本项目现状与缺口 | 规范文档中的对齐要求 |
|-----------|----------|------------------|------------------------|
| 验证码回填 | 输入框用 get_by_role/get_by_placeholder，等可见再 fill | 部分组件仍用 locator(selector) + count()>0 | 规定验证码输入框用 get_by_role/get_by_placeholder，先 wait 可见再 fill |
| 弹窗（可预期） | 流程内显式 wait 关闭按钮可见再点击 | 多依赖执行器步骤边界轮询，组件内显式 wait 不统一 | 已知某步会弹窗时，流程内显式 wait 到该弹窗可见再点击关闭/确认 |
| 业务 Modal/Dialog | 操作后 wait_for(visible)/expect，再 get_by_role 点确定/取消 | 大量 locator+固定 wait_for_timeout | 禁止用固定 timeout 替代「等对话框出现」；规定 wait 到可见→get_by_role("button", name="…") 点击 |
| Toast / 会话过期 / 加载 | 成文约定（不主动关 Toast；URL/特征检查会话；条件等加载） | 无集中文档约定 | 在场景小节中写明：Toast 多不主动关、会话过期与「已登录则跳过」契约一致、加载以目标可见或 loading 消失为条件 |
| 元素检测 | 可重试等待，禁止单次 count()+is_visible() 后即操作 | 组件内与 popup 轮询中仍有 count()+is_visible() | 禁止单次检测；规定 expect(locator).to_be_visible() 或 wait_for(state="visible") 或直接对 locator 操作 |
| 不可预期遮挡 | 执行器轮询 或 add_locator_handler | 仅执行器轮询，未使用 handler | 说明可依赖执行器步骤边界 close_popups；使用 add_locator_handler 时 handler 内仅自包含 click，防死循环，并注明 focus/mouse 状态影响 |
| iframe 内元素 | frame_locator 或 page.frames 后再定位 | 已有 frames 遍历，规范未成文 | 规定：操作前选定 frame，再在 frame 上定位与 wait/click；弹窗在 iframe 内时在对应 frame 执行 |
| iframe 与交互框类型 | 罗列主流 iframe 与交互框/信息框类型及各类业界检测/应对 | 规范未罗列类型与检测/应对表 | 规范须包含「主流 iframe 与交互框/信息框类型」表（同源/跨域业务与组件 iframe、Modal/Drawer/Popover）及「业界检测方式」「业界应对方式」按类型表格，便于按类型选用；可引用提案中表格 |
| 新标签页 | expect_event("page")，在新 page 操作后 close | 部分组件监听 page 事件，规范未写 | 规定：若导出/下载会打开新标签页，先 expect_event("page") 再点击，新 page 上操作后 close |
| 下载路径 | context accept_downloads + downloads_path 约定 | 执行器已设置，规范未写 | 规定：脚本假定 context 已设置 accept_downloads 与 downloads_path；组件仅用任务目录保存 |
| 长时间生成 | 等「生成中」消失或「下载」按钮出现，条件等待 | 已有轮询与 processing_indicators，规范未写 | 规定：以文案消失或下载按钮可见为条件，较长 timeout，避免固定长 sleep |
| 平台限流 | 检测限流文案/429，退避重试 | 有重试与 backoff，未明确限流检测 | 规定：检测到限流文案或 429 时退避重试；可选步骤间短延时 |
| 页面崩溃/超时 | 重试或快速失败，明确错误类型 | 有 try/except，未区分可重试与不可重试 | 规定：关键步骤配合重试；page/context 关闭或超时时视策略重试或快速失败并明确错误类型 |
| 多语言/多站点 | get_by_role 优先，或配置多语言文案 | 选择器有注明多语言风险，未成文 | 规定：按钮优先 get_by_role；若用文案则从配置读取多语言候选并注明改版风险 |
| 每域前后会话 | 域前/域后检查 URL 或登录页特征 | 有「已登录跳过」，未明确每域检查 | 规定：每域导出前或后可检查是否被重定向到登录页，掉线则重新登录后再继续 |
| 导出阶段验证码 | 与登录同一套流程 | 验证码提案已约定，规范未显式写 | 规定：导出阶段出现验证码与登录阶段同一套（检测→暂停→回传→同 page 继续） |
| Shadow DOM | locator 默认穿透 shadow，规范注明即可 | 未成文 | 规定：元素在 Shadow Root 内时 Playwright 默认穿透，规范注明避免误判 |
| 动态列表/Stale | 每次再查或带唯一 key，避免长期持有 locator | 未成文 | 规定：虚拟列表或复用 DOM 的列表，每次按当前 DOM 再查或带唯一 key，避免 stale 错位 |
| Cookie 接受/拒绝 | 显式 wait 接受/拒绝再点击，选择器可配置 | 弹窗仅写「关闭」 | 规定：需合规选择时 wait 到接受/拒绝按钮再点击，选择器可放 popup_config |
| SPA 路由/导航 | 等目标页特征或 URL+特征再继续 | 未单独成场景 | 规定：SPA 导航后等目标页特征元素可见（或 URL 变化+特征），不用固定 sleep |
| 虚拟列表/无限滚动 | 滚动入视口或触底加载后对目标 wait_for | 未单独成场景 | 规定：先滚动使目标入视口或触底加载，再对目标条件等待 |
| 文件上传 | set_input_files，不 click 开系统对话框 | 未单独列 | 规定：用 locator('input[type=file]').set_input_files(path)；有进度则按加载中等待 |
| 空状态/无数据 | 先判断非空或有数据特征再操作 | 未单独列 | 规定：依赖列表有数据的流程前，先判断非空或等有数据特征再导出/操作 |
| 浏览器权限弹窗 | 步骤边界关闭或 handler；需自动选则配置选择器 | 可算不可预期遮挡，未单独列 | 规定：可依赖执行器或 add_locator_handler；需自动选时配置选择器 |
| 多步向导 | 每步后 wait 下一步或结果区域可见 | 可被「操作后 wait」覆盖，未显式写 | 规定：多步流程每步后等下一步按钮或结果区域可见再继续 |
| 网络/请求失败 | 重试或快速失败，明确错误类型 | 有超时，未区分请求失败/离线 | 规定：接口失败/离线按策略重试或快速失败，与页面超时区分 |
| 分页（Pagination） | 点击后等当前页/列表刷新再继续 | 未单独成场景 | 规定：分页点击后等当前页内容或列表刷新再继续，可归入加载中或条件等待 |
| API 与版本 | 以当前文档与 API 为准 | 未注明 | 规范可注明：以 Playwright Python 当前文档与 API 为准，避免 API 升级后歧义 |

已与业界对齐、规范仅需文档化或引用：验证码「检测→暂停→同页回传→继续」、执行器 close_popups 时机与配置、会话复用（reused_session）、下载先 expect_download 再 click。

### 3. 可选：在 data-collection 能力中增加「采集脚本编写规范」需求

- 在 `openspec/specs/data-collection/spec.md` 中通过本变更的 spec delta **ADDED** 一条需求：系统（及贡献者）编写或修改采集 Python 组件时 SHALL 遵循《采集脚本编写规范》中的定位、等待与契约约定。
- 实现方式为「文档 + 代码审查/新人指引」，不强制一次性改造所有既有组件。

### 4. 不修改

- 不强制立即重构现有组件；不修改执行器或适配层接口。
- 不新增 CI 检查（可选后续再考虑静态/规则检查）。

## Impact

### 受影响的规格

- **data-collection**：可选 ADDED 一条「采集脚本编写规范」需求（见上）。

### 受影响的代码与文档

| 类型     | 位置                                               | 修改内容                         |
|----------|----------------------------------------------------|----------------------------------|
| 新增文档 | `docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md` 等 | 采集脚本编写规范（定位/等待/契约/临时弹窗与遮挡层/**各场景与业界设计**；**iframe 与交互框/信息框类型**及业界检测/应对表；**现代化网页补充场景**：Shadow DOM、SPA 路由、虚拟列表/无限滚动、文件上传、Cookie 接受/拒绝、空状态、权限弹窗、多步向导、网络/请求失败、**分页**；**API 与版本**注明；**真实采集环境**：iframe、新标签页、下载路径、长时间生成、平台限流、页面崩溃/超时、多语言、每域会话检查、导出阶段验证码等） |
| 可选     | `openspec/specs/data-collection/spec.md`           | ADDED 规范遵循需求与 Scenario    |

### 不修改

- 不修改 `modules/apps/collection_center/` 执行逻辑。
- 不修改现有 `modules/platforms/*/components/*.py` 的必须行为（仅可选在文档中引用为示例或反例说明）。

## Non-Goals

- 不在本变更内完成对所有既有组件的 locator/wait 重构。
- 不引入自动化脚本规范检查（如自定义 lint 规则）。
- 不在本变更内强制实现「页面崩溃后自动重建 page」等执行器逻辑；规范仅要求**文档化**这些情况的检测与应对（重试或快速失败、明确错误类型），实现策略由执行器或上层决定。
