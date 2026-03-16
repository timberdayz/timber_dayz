# 采集脚本编写规范

本文档为西虹 ERP 数据采集相关 Python 组件（登录、导航、导出等）的**唯一成文编写依据**，使后续新增与修改采集脚本可按业界主流方式编写（Playwright 官方推荐 + 各打断类场景的检测与应对），并与现有执行器、验证码提案、popup_handler 契约一致。

**API 与版本**：本规范以 **Playwright Python 当前文档与 API** 为准。若 Playwright 升级导致 sync/async 或方法签名变更，请以官方文档为准，避免歧义。

---

## 1. 元素定位

- **优先使用**：`page.get_by_role()`、`page.get_by_label()`、`page.get_by_text()`；避免依赖易变的 CSS 类、ID 或复杂 XPath。
- **唯一性强约束（strict mode）**：对将被 `click()/fill()/press()/expect(...).to_be_visible()` 使用的 locator，必须保证在当前作用域内唯一命中（推荐 `expect(locator).to_have_count(1)` 或等价唯一性保障），禁止依赖“碰巧只匹配一个”。
- **先收敛作用域，再定位元素**：优先在稳定容器（如 `form`、`[role='dialog']`、表格行、卡片根节点、目标 iframe）内再 `get_by_*`；避免直接在 `page` 根上用宽泛选择器。
- **限制使用 `.first` / `.nth()`**：仅在业务语义明确是“第 N 个”的场景使用，并在代码注释说明依据；禁止把 `.first` 当作消除歧义的默认手段。
- **若必须使用** `locator(selector)`：将选择器集中在平台 `*_config.py` 中，并注明多语言/改版风险。
- **多语言/多站点**：按钮优先 `get_by_role`；若用文案则从配置读取多语言候选（如「确定」「OK」）或集中至 `*_config` 并注明语言/改版风险。
- **iframe 内元素**：操作前先用 `page.frame_locator("iframe").first` 或选定 `page.frames`，再在该 frame 上做 locator/wait/click；关闭弹窗时若弹窗在 iframe 内，需在对应 frame 上执行（与 popup_handler 遍历 frames 一致）。具体类型与检测/应对见本文「iframe 与交互框类型及业界检测/应对」一节。
- **Shadow DOM**：若元素在 Shadow Root 内，Playwright 的 locator **默认穿透 shadow**，无需额外写法；规范注明此点，避免误判「无此元素」。
- **动态列表/Stale**：对虚拟列表或框架复用 DOM 的列表，优先每次按当前 DOM 再查（如用文本/role 再 locator）或使用带唯一 key 的 selector，避免长期持有可能被复用的 locator 导致点击错位。

---

## 2. 元素检测与可重试等待

- **禁止**：仅用「单次」`loc.count() > 0 and await loc.first.is_visible()` 后即操作。在慢网或动画未结束时，单次检测易失败且不重试。
- **禁止**：`count()+is_visible()` 仅做一次判断后立刻交互，或通过 `try/except Exception: pass` 吞掉定位失败继续执行。
- **应使用**以下可重试方式之一：
  - `expect(locator).to_be_visible()`（Python API）
  - `locator.wait_for(state="visible", timeout=...)`
  - 直接对 locator 执行 `click()`/`hover()`/`fill()`，依赖 Playwright 的 actionability 自动等待
- 需要交互前确认唯一性时，可在显式等待后增加 `expect(locator).to_have_count(1)`，若不唯一应快速失败并输出诊断信息（页面 URL、作用域、候选数量）。
- 需要「等某元素出现再继续」时用**条件等待**，不用固定 `wait_for_timeout` 替代。

---

## 3. 等待策略

- **优先**：Playwright 自动等待或显式条件等待（如 `expect(locator).to_be_visible()`、`locator.wait_for(state="visible")`）。
- **仅在确需「人为节奏」时**使用 `wait_for_timeout`，并**注明原因**。

---

## 4. 复杂交互（悬停→内容出现→点击）

模拟真人操作（如下拉菜单、级联菜单）时，推荐流程：

1. 对触发元素：`locator.hover()`（或 `click()` 若需点击才出现）
2. 对下拉/菜单/弹出层：`menu_locator.wait_for(state="visible")` 或 `expect(menu_locator).to_be_visible()`，**勿用固定毫秒替代**
3. 对菜单项：优先 `get_by_role("menuitem", name="...")` 或 `get_by_text()` 等稳定定位
4. 视需 `scroll_into_view_if_needed()`、`item.hover()` → `item.click()`
5. 优先 locator 的 hover/click；`page.mouse.move()`/`down()`/`up()` 仅作兜底。

---

## 5. 组件契约

### 5.1 基类层次结构

所有采集组件必须继承 `modules/components/` 中的基类。禁止直接继承 `object` 或创建独立的 Result 类。

| 基类 | `run` 签名 | 返回类型 | 路径 |
|------|-----------|---------|------|
| `LoginComponent` | `run(self, page) -> LoginResult` | `LoginResult(success, message, profile_path)` | `modules/components/login/base.py` |
| `ExportComponent` | `run(self, page, mode=...) -> ExportResult` | `ExportResult(success, message, file_path)` | `modules/components/export/base.py` |
| `NavigationComponent` | `run(self, page, target) -> NavigationResult` | `NavigationResult(success, message, url)` | `modules/components/navigation/base.py` |
| `DatePickerComponent` | `run(self, page, option) -> DatePickResult` | `DatePickResult(success, message, option)` | `modules/components/date_picker/base.py` |

### 5.2 ExecutionContext（统一执行上下文）

账号和配置信息通过 `self.ctx` 获取，**不通过 `run` 参数传递**：

```python
acc = self.ctx.account or {}        # username, password(已解密), login_url, store_name, ...
config = self.ctx.config or {}      # params, task, default_login_url, ...
params = config.get("params") or {} # captcha_code, otp, login_url_override, ...
```

| 字段 | 类型 | 用途 |
|------|------|------|
| `platform` | `str` | 平台标识（"miaoshou", "shopee" 等） |
| `account` | `dict` | 账号信息（password 由适配层解密） |
| `config` | `dict` | 任务配置（日期范围、下载目录、验证码回传等） |
| `logger` | `SupportsLogger` | 通过 `self.logger` 属性访问 |
| `is_test_mode` | `bool` | 测试模式标志（影响 `guard_overlays` 行为） |

### 5.3 内置方法

| 方法 | 用途 | 调用时机 |
|------|------|---------|
| `self.guard_overlays(page, label=...)` | 关闭弹窗/通知（仅测试模式生效） | 导航后、关键交互前 |
| `self.report_step(event_type, step_id, action=...)` | 步骤进度上报 | 每个关键步骤前后 |

### 5.4 下载与文件约定

- 脚本假定 **context 已设置 `accept_downloads=True` 且 `downloads_path` 为任务下载目录**；组件仅使用传入的 `download_dir`/`ctx.config` 内路径保存文件。
- 导出组件使用 `build_standard_output_root(ctx, data_type, granularity)` 计算输出目录。

### 5.5 验证码契约

- 验证码恢复路径**必须在 `page.goto` 之前**（避免重试时刷新页面丢失已填内容）。
- 检测到验证码时 `raise VerificationRequiredError(type, screenshot_path)` 暂停等待回传。
- 恢复路径从 `config["params"]["captcha_code"]` 或 `config["params"]["otp"]` 读取回传值。

完整模板参见 `docs/guides/PYTHON_COMPONENT_TEMPLATE.md`。

---

## 6. 错误与重试

- 关键步骤配合 `RetryStrategy` 或组件内重试。
- **平台限流/429/「请稍后再试」**：检测页面限流文案或 HTTP 429，退避后重试（与现有 backoff 一致）。
- **page/context 关闭或导航超时**：视策略重试或快速失败，并返回明确错误类型，便于上层区分可重试与不可重试。
- **网络离线/请求失败**（接口 5xx、超时、离线）：按策略重试或快速失败并明确错误类型，与「页面超时」区分便于上层处理。
- 可选引用：Playwright 官方 [Best Practices](https://playwright.dev/python/docs/best-practices)、[Actionability](https://playwright.dev/python/docs/actionability)、[Locators](https://playwright.dev/python/docs/locators)；项目内已符合规范的示例（如部分使用 `get_by_role` 的登录组件、妙手导出中的 getByRole menuitem）可在文档中引用。

---

## 7. 临时弹窗与遮挡层

- **执行器**：在**登录前、每个数据域导出前**会调用通用弹窗处理（`close_popups`），使用通用 + 平台配置（`modules/platforms/<platform>/popup_config.py` 的 `get_close_selectors()` / `get_overlay_selectors()`）与 ESC 关闭常见弹窗。
- **组件内已知弹窗**：若某步会弹出对话框（如「确定」「导出」），应在流程中**显式** wait 到该对话框可见再点击关闭/确认。
- **不可预期弹窗**：可依赖执行器在步骤边界的关闭，或选用 `page.add_locator_handler`（会改变 focus/mouse 状态，须在文档中注明）。
- **Cookie 合规选择**：需主动点「全部接受」或「全部拒绝」时，显式 wait 到对应按钮再点击，选择器可放平台 popup_config。
- **浏览器权限弹窗**（通知/位置/麦克风等）：可依赖执行器步骤边界关闭或 add_locator_handler；需自动选允许/拒绝时配置选择器。

---

## 8. 各场景下如何编写脚本（场景与业界设计）

以下列出各场景的**业界主流检测方式**与**应对方式**，以及**本项目中脚本应如何编写**（与验证码提案、popup_handler、组件契约对齐）。表格见下「场景列表」「检测与应对概要」；缺口与对齐要求见「现状与业界对照」。

### 8.1 场景要点摘要

| 场景                         | 本项目编写要点                                                                                                                                           |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 临时验证码（OTP/图形）       | 检测用 DOM/文案；输入框用 get_by_role/get_by_placeholder，等可见再 fill；导出阶段与登录同一套：检测→VerificationRequiredError→暂停→回传→同 page 填入继续 |
| 临时弹窗（Cookie/公告/促销） | 可预期：流程内 wait 关闭按钮再点击；不可预期：依赖执行器 close_popups 或 add_locator_handler；合规选择时显式 wait 接受/拒绝再点击                        |
| 临时遮罩（Modal/Dialog）     | 操作后对预期对话框 wait_for(visible)/expect，再 get_by_role("button", name="确定") 等点击；禁止固定 wait_for_timeout                                     |
| Toast/Snackbar               | 多不主动关；若挡点击可 wait_for(state="hidden") 或短等                                                                                                   |
| 会话过期/重定向登录          | 关键步后检查 URL 或登录页特征；每域导出前或后可检查是否被重定向到登录页，掉线则重新登录后再继续                                                          |
| 加载中/骨架屏                | 以目标元素可见或 loading 消失为条件等待；长时间生成/异步导出以文案消失或「下载」按钮可见为条件（较长 timeout），不用固定长 sleep                         |
| 下载确认/文件弹窗            | 先 context.expect_download() 再点击；若有确认框先 wait 再点；新标签页：expect_event("page") 再点击，新 page 上操作后 close；仅用任务目录保存             |
| 不可预期遮挡                 | 执行器步骤边界轮询或 add_locator_handler（handler 内仅自包含 click，防死循环）；注明 focus/mouse 状态影响                                                |

### 8.2 场景列表

| 场景类型                     | 典型表现                                | 常见触发时机             |
| ---------------------------- | --------------------------------------- | ------------------------ |
| 临时验证码（OTP）            | 短信/邮箱验证码输入框、「验证码已发送」 | 登录/2FA                 |
| 临时验证码（图形）           | 「请输入验证码」+ 图形/输入框           | 登录错误、风控或始终出现 |
| 临时弹窗（Cookie/公告/促销） | Cookie 同意条、公告/促销弹窗            | 首访、定时或随机         |
| 临时遮罩（Modal/Dialog）     | 需点击「确定/关闭」的对话框             | 导出/删除等操作后        |
| 临时消息（Toast/Snackbar）   | 顶部/底部短时提示                       | 操作成功/失败反馈        |
| 会话过期/重定向登录          | 被重定向到登录页、出现登录表单          | 会话超时、多端登出       |
| 加载中/骨架屏                | loading 动画、骨架块、按钮 disabled     | 页面/列表/接口未就绪     |
| 下载确认/文件弹窗            | 导出后「导出/确定/开始导出」等          | 导出流程中的二次确认     |
| 不可预期遮挡                 | 任意时间出现的浮层、插播                | 难以用固定步骤描述       |
| iframe 内操作                | 按钮/表单在 iframe 内                   | 导出、选择字段等         |
| 新标签页弹出                 | 点击后打开新 tab，下载或确认在新页      | 部分平台导出流程         |
| 长时间生成/异步导出          | 「生成中」「处理中」数分钟后才可下载    | 报表/订单导出            |
| 平台限流/操作频繁            | 429、「请稍后再试」「操作过于频繁」     | 短时多次导出或操作过快   |
| 页面崩溃/导航超时            | page/context 关闭、导航超时             | 网络抖动、目标站异常     |
| Shadow DOM                   | 组件在 shadow root 内                   | 现代组件库、微前端       |
| SPA 路由/导航                | 点击后仅前端路由切换、无整页 reload     | 单页应用内跳转           |
| 虚拟列表/无限滚动            | 仅渲染可见项，滚动才加载更多 DOM        | 长列表、报表             |
| 文件上传（input file）       | 「选择文件」触发上传或导入              | 导入、附件               |
| Cookie 接受/拒绝             | 需主动点「全部接受」或「全部拒绝」      | 合规、首访               |
| 空状态/无数据                | 列表无数据时按钮禁用或隐藏              | 导出前、筛选后           |
| 浏览器权限弹窗               | 通知/位置/麦克风等浏览器级弹窗          | 部分站点请求权限         |
| 多步向导（Stepper/Wizard）   | 多步流程，每步「下一步」                | 导出/配置向导            |
| 网络/请求失败                | 接口 5xx、超时、离线                    | 弱网、服务异常           |
| 分页（Pagination）           | 点击下一页后列表/内容刷新               | 列表多页、报表分页       |

### 8.3 检测与应对概要（业界主流）

| 场景                 | 检测方式（主流）                                            | 应对方式（主流）                                                                  |
| -------------------- | ----------------------------------------------------------- | --------------------------------------------------------------------------------- |
| OTP / 图形验证码     | DOM/文案（输入框、提示）；有头/无头同一套                   | 检测→暂停→人工或合规回填→同 page fill+click 继续                                  |
| Cookie/公告/促销弹窗 | 显式 wait 到关闭按钮可见，或 add_locator_handler/步骤前轮询 | 可预期：流程内 wait+点击；不可预期：handler 或步骤边界轮询                        |
| 业务 Modal/Dialog    | 操作后对预期 dialog 做 wait_for(visible)/expect             | wait 到可见→get_by_role 点确定/取消                                               |
| Toast/Snackbar       | 需断言时定位容器+wait 可见；防挡点击可 wait hidden          | 多不主动关；必要时等消失或短等                                                    |
| 会话过期             | URL/登录表单/成功页特征；关键步后或周期检查                 | 重新登录或注入 storage_state，继续                                                |
| 加载中/骨架屏        | 等目标元素可见或 loading 元素 hidden                        | 对目标元素直接操作或显式 wait                                                     |
| 下载确认             | 先 expect_download 再 click；确认框 wait_for(visible)       | 先注册 expect_download→点击→若有确认框 wait+点按钮                                |
| 不可预期遮挡         | add_locator_handler 或步骤边界轮询                          | handler 内自包含 click；或执行器轮询关闭                                          |
| iframe 内操作        | frame_locator 或选定 page.frames 后再定位                   | 在选定 frame 上 locator/wait/click；弹窗在 iframe 内时在对应 frame 关闭           |
| 新标签页             | expect_event("page") 再点击，在新 page 操作后 close         | 在新 page 上 wait/点击/等下载，然后 new_page.close()                              |
| 长时间生成           | 等「生成中」等文案消失或「下载」按钮出现                    | 条件等待 + 较长 timeout；可配置 processing_indicators                             |
| 平台限流             | 检测限流文案或 429，退避重试                                | 退避后重试；必要时步骤间短延时                                                    |
| 页面崩溃/超时        | 重试或快速失败，明确错误类型                                | RetryStrategy 或快速失败，区分可重试与不可重试                                    |
| Shadow DOM           | Playwright locator 默认穿透 shadow                          | 规范注明默认穿透，避免误判无此元素                                                |
| SPA 路由/导航        | URL 或目标页特征元素                                        | 等目标页特征元素可见（或 URL+特征）再继续，不用固定 sleep                         |
| 虚拟列表/无限滚动    | 目标是否在 DOM、加载更多是否消失                            | 先滚动使目标入视口或触底加载，再对目标 wait_for；或等加载更多消失后 wait_for 目标 |
| 文件上传             | input[type=file] 存在                                       | locator('input[type=file]').set_input_files(path)；有进度则按加载中/条件等待      |
| Cookie 接受/拒绝     | wait 到接受/拒绝按钮可见                                    | 显式 wait 再点击，选择器可配置                                                    |
| 空状态/无数据        | 列表非空或「有数据」特征                                    | 先判断非空或等有数据特征，再执行导出/操作                                         |
| 浏览器权限弹窗       | 步骤边界或 handler 检测                                     | 执行器轮询关闭或 add_locator_handler；需自动选时配置选择器                        |
| 多步向导             | 每步后下一步/结果区域                                       | 每步后 wait 下一步按钮或结果区域可见再继续                                        |
| 网络/请求失败        | 接口失败、超时、离线                                        | 重试或快速失败，明确错误类型，与页面超时区分                                      |
| 分页（Pagination）   | 当前页内容或列表已刷新                                      | 点击下一页后等当前页内容或列表刷新再继续，不用固定 sleep                          |

---

## 9. iframe 与交互框/信息框类型及业界检测/应对

### 9.1 主流 iframe 与交互框/信息框类型

| 类型                                | 典型表现                       | 常见场景                                                                      | 同源/跨域          |
| ----------------------------------- | ------------------------------ | ----------------------------------------------------------------------------- | ------------------ |
| 同源业务 iframe                     | 后台内嵌的报表、表单、字段选择 | 导出字段选择（如 iframe[title*='选择导出字段']）、列表/表格内嵌、筛选面板     | 同源               |
| 同源组件 iframe                     | 日期/时间选择、富文本、图表    | 日期控件在 iframe 内（如 EDS arco-picker）、部分 UI 库把复杂控件放在 iframe   | 同源               |
| 跨域登录/认证 iframe                | 第三方登录、OAuth、SSO 登录框  | 平台内嵌「用 XX 账号登录」                                                    | 跨域               |
| 跨域支付/安全 iframe                | 支付、验证码、人机验证         | reCAPTCHA、支付网关                                                           | 跨域               |
| 跨域广告/统计 iframe                | 广告、埋点、客服               | 广告位、客服浮窗                                                              | 跨域               |
| Modal/Dialog（主文档）              | 页内对话框+遮罩                | 确认框、导出进度、错误提示（.jx-dialog\_\_body、.ant-modal、[role="dialog"]） | 主文档             |
| Drawer/侧边抽屉                     | 从侧边滑出的面板               | 筛选、设置、详情                                                              | 主文档或 iframe 内 |
| Popover/Dropdown（主文档或 iframe） | 气泡、下拉菜单                 | 导出下拉「导出全部订单」、日期快捷项                                          | 主文档或 iframe 内 |

### 9.2 业界检测方式（按类型）

| 对象                      | 检测方式                                                                                  | 说明                                                     |
| ------------------------- | ----------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| 是否有 iframe             | page.frames（可递归 child_frames）                                                        | 取 Frame 列表，再在目标 frame 上 frame.locator(...)      |
| 用选择器锁定 iframe       | page.frame_locator("iframe").first 或 iframe[title*=...]                                  | 有 title/name 时更稳，选择器可配置（如 iframe_locators） |
| iframe 是否就绪           | 在 frame 内等 body 或关键元素 wait_for                                                    | 避免未加载完就操作；若 iframe 会刷新需轮询或短时重试     |
| Modal/Dialog（主文档）    | page.locator('.ant-modal, .jx-dialog\_\_body, [role="dialog"]').wait_for(state='visible') | 先等容器出现，再在主文档上 locator                       |
| Modal 内嵌 iframe         | 先等主文档 dialog 可见，再 dialog.locator('iframe') 或 page.frame_locator('iframe')       | 弹窗内容在 iframe 里时，在 frame 内定位按钮/表单         |
| 交互框在主文档还是 iframe | 主文档先试 page.get_by_role/page.locator；若无再遍历 page.frames 或 frame_locator         | 与「Prefer dialog in main page; fallback to iframe」一致 |

### 9.3 业界应对方式（按类型）

| 类型                      | 应对方式                                                                                                                                                             | 注意点                                                                        |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| 同源业务 iframe           | frame_locator(selector).first 或从 page.frames 选目标 frame，再 frame.locator(...).click()；选择器集中配置（如 iframe_locators + 内部按钮）                          | 优先用 iframe 的 title/name 做 selector；内部元素优先 get_by_role/get_by_text |
| 同源组件 iframe（如日期） | 递归 page + frames/child_frames 为 roots，在每个 root 上找面板容器（如 .arco-picker-dropdown），在该 root 上 click；或单一 iframe 时用 frame_locator("iframe").first | iframe 会刷新/延迟加载时需 wait_for 或短轮询                                  |
| 跨域 iframe               | 能操作的：等 load 后在同一 context 内 frame_locator/frame 操作。受同源限制的：仅检测存在（如验证码 iframe），走暂停→人工/打码→回传，不跨域操作 DOM                   | 与验证码提案一致                                                              |
| Modal/Dialog（主文档）    | wait_for(visible) 到对话框容器，再 page 上 get_by_role("button", name="确定") 等点击                                                                                 | 不用固定 timeout 替代等对话框出现                                             |
| Modal 内嵌 iframe         | 先等主文档 dialog 可见；内容在 iframe 则 page.frame_locator('iframe').first 内勾选/点击导出，再回主文档点确定/关闭                                                   | 与「先 dialog 再 iframe 兜底」一致                                            |
| Popover/Dropdown          | 主文档：trigger hover/click → menu_locator.wait_for(visible) → get_by_role("menuitem", name="...")；在 iframe 内则先进入对应 frame 再同样流程                        | 与复杂交互规范一致                                                            |

---

## 10. 现代化网页补充场景

按业界主流写明以下场景的检测与应对：

| 场景                           | 检测与应对要点                                                                                                            |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| **Shadow DOM**                 | Playwright locator 默认穿透 shadow，规范注明即可，避免误判无此元素                                                        |
| **SPA 路由/导航**              | 点击后仅前端路由切换、无整页 reload 时，先等**目标页特征元素**可见（或 URL 变化 + 特征）再继续，不用固定 sleep            |
| **虚拟列表/无限滚动**          | 先滚动使目标进入视口或触底加载，再对目标元素条件等待；或等「加载更多」消失后对目标 locator wait_for                       |
| **文件上传（input file）**     | 用 `locator('input[type=file]').set_input_files(path)`，不通过 click 打开系统对话框；若有上传进度则按「加载中」或条件等待 |
| **Cookie 接受/拒绝**           | 需合规选择时显式 wait 到「全部接受」或「全部拒绝」按钮再点击，选择器可配置                                                |
| **空状态/无数据**              | 依赖「列表有数据」的流程前，先判断非空状态或等「有数据」特征，再执行导出/操作，避免对禁用或隐藏按钮操作                   |
| **浏览器权限弹窗**             | 可依赖执行器步骤边界关闭或 add_locator_handler；需自动选时配置选择器                                                      |
| **多步向导（Stepper/Wizard）** | 每步操作后等「下一步」按钮或本步结果区域可见再继续，不用固定延时替代                                                      |
| **网络/请求失败**              | 接口 5xx、超时、离线时按策略重试或快速失败，明确错误类型，与页面超时区分                                                  |
| **分页（Pagination）**         | 点击「下一页」后等**当前页内容或列表刷新**再继续取数或操作，可归入加载中或条件等待，不用固定 sleep                        |

---

## 11. 现状与业界对照（规范文档中的对齐要求）

撰写或审查脚本时，以下缺口已在本文各小节中明确对齐方式，使编写者按业界主流落笔：

| 场景/维度               | 规范文档中的对齐要求                                                                                                           |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| 验证码回填              | 验证码输入框用 get_by_role/get_by_placeholder，先 wait 可见再 fill                                                             |
| 弹窗（可预期）          | 已知某步会弹窗时，流程内显式 wait 到该弹窗可见再点击关闭/确认                                                                  |
| 业务 Modal/Dialog       | 禁止用固定 timeout 替代「等对话框出现」；规定 wait 到可见→get_by_role("button", name="…") 点击                                 |
| Toast / 会话过期 / 加载 | Toast 多不主动关；会话过期与「已登录则跳过」契约一致；加载以目标可见或 loading 消失为条件                                      |
| 元素检测                | 禁止单次检测；规定 expect(locator).to_be_visible() 或 wait_for(state="visible") 或直接对 locator 操作                          |
| 不可预期遮挡            | 可依赖执行器步骤边界 close_popups；使用 add_locator_handler 时 handler 内仅自包含 click，防死循环，并注明 focus/mouse 状态影响 |
| iframe 内元素           | 操作前选定 frame，再在 frame 上定位与 wait/click；弹窗在 iframe 内时在对应 frame 执行                                          |
| 新标签页                | 若导出/下载会打开新标签页，先 expect_event("page") 再点击，新 page 上操作后 close                                              |
| 下载路径                | 脚本假定 context 已设置 accept_downloads 与 downloads_path；组件仅用任务目录保存                                               |
| 长时间生成              | 以文案消失或下载按钮可见为条件，较长 timeout，避免固定长 sleep                                                                 |
| 平台限流                | 检测到限流文案或 429 时退避重试；可选步骤间短延时                                                                              |
| 页面崩溃/超时           | 关键步骤配合重试；page/context 关闭或超时时视策略重试或快速失败并明确错误类型                                                  |
| 多语言/多站点           | 按钮优先 get_by_role；若用文案则从配置读取多语言候选并注明改版风险                                                             |
| 每域前后会话            | 每域导出前或后可检查是否被重定向到登录页，掉线则重新登录后再继续                                                               |
| 导出阶段验证码          | 导出阶段出现验证码与登录阶段同一套（检测→暂停→回传→同 page 继续）                                                              |
| 动态列表/Stale          | 虚拟列表或复用 DOM 的列表，每次按当前 DOM 再查或带唯一 key，避免 stale 错位                                                    |
| 分页（Pagination）      | 分页点击后等当前页内容或列表刷新再继续，可归入加载中或条件等待                                                                 |
| API 与版本              | 以 Playwright Python 当前文档与 API 为准，避免 API 升级后歧义                                                                  |

**当前覆盖状态**：规范已覆盖主流场景（验证码、弹窗、iframe、下载、会话等），但仍需持续校准（如 locator 唯一性、失败可观测性、旧模板清理）以避免实现回退。

---

## 12. 参考

- Playwright Python： [Best Practices](https://playwright.dev/python/docs/best-practices)、[Actionability](https://playwright.dev/python/docs/actionability)、[Locators](https://playwright.dev/python/docs/locators)
- 项目内：验证码提案（add-web-captcha-optimization）、`modules/apps/collection_center/popup_handler.py` 及平台 `popup_config.py`；可引用已使用 `get_by_role` 的登录组件、妙手导出中的 menuitem 等作为示例。

---
## 13. 工程强约束

以下五条契约为必须遵守的工程约束，用于避免"录制可跑、线上不稳"的常见问题。
违反其中任一条即视为代码缺陷，需在合入前修复。

1. **定位器唯一性契约** -- 所有交互目标都必须满足"在当前作用域唯一"；出现多个候选时，必须先收敛作用域（form/dialog/frame/row）再定位；仍不唯一时应快速失败并产出可诊断信息（URL、作用域、候选数量），禁止静默回退到 `.first`。
2. **导航完成契约（SPA/MPA 通用）** -- 不以单一 `networkidle` 作为成功条件；使用"URL/路由特征 + 页面关键元素可见"双信号确认页面就绪。
3. **动态 DOM 契约** -- 对虚拟列表、重渲染、iframe 刷新场景，在关键交互前重新定位元素；禁止长期持有可能失效的 locator 引用跨步骤复用。
4. **异常可观测性契约** -- 关键失败必须包含：阶段（login/navigation/export/...）、组件名、版本、URL、核心选择器信息；验证码/关键错误路径需保留截图。
5. **等待与重试预算契约** -- 每个关键步骤定义 timeout 与重试上限；达到上限后快速失败并返回结构化错误，禁止无限轮询或无终止重试。

### 禁止的反模式

| 反模式 | 为何禁止 | 正确做法 |
|--------|---------|---------|
| `.first`/`.nth()` 掩盖多匹配（无业务语义说明） | 隐藏定位不精确的问题 | 先收敛作用域；详见第 16 节 |
| `count() > 0 and is_visible()` 单次判断后操作 | 慢网/动画下易失败 | `expect(locator).to_be_visible()` 或 `wait_for(state="visible")` |
| 固定 `wait_for_timeout`/`sleep` 替代条件等待 | 不可靠且浪费时间 | 条件等待（第 2、3 节） |
| `except Exception: pass` 吞异常 | 隐藏真实失败原因 | 至少记录警告日志，或重新抛出 |
| 异步组件中使用同步 Playwright 调用链 | 阻塞事件循环 | 全部使用 `async_playwright` + `await` |

---

## 14. 文档治理约定

- 本文档是采集脚本编写的**唯一规范基线**；其他录制/模板文档不得与本规范冲突。
- 若示例文档仅作历史参考，必须显式标注"历史/废弃"，并链接到本文档。
- 任何新增录制模板在合入前需通过本规范一致性审查（定位器唯一性、等待策略、异常可观测性三项必查）。
- 组件编写模板见 `docs/guides/PYTHON_COMPONENT_TEMPLATE.md`（以实际基类为准）。

---

## 15. 生成器 vs 运行时职责边界

生成器（`steps_to_python.py`）和运行时（`test_component.py`、`executor_v2.py`）各自承担不同职责，不得混淆：

### 生成器职责（组件代码内）

| 职责 | 说明 |
|------|------|
| URL 导航 | `_target_url` 来源优先级（override > account > config > platform default） |
| 步骤回放 | 忠实转换录制步骤为 Playwright 操作（click/fill/wait 等） |
| 验证码处理 | 检测到验证码步骤时 raise VerificationRequiredError |
| 组件元数据 | platform/component_type/data_domain 等类属性 |
| 成功条件模板 | TODO 注释引导用户编辑（如 wait_for_url） |
| click+fill 合并 | 相邻 click 与 fill 操作同选择器时自动合并为单个 fill |
| 容器上下文 | 有 `metadata.container_selector` 时生成 `_form = page.locator(...)`，否则 `_form = page` |

### 运行时职责（框架层）

| 职责 | 说明 |
|------|------|
| 页面就绪检测 | 执行 login 组件前确认关键元素可见（使用 `.first.wait_for`） |
| 会话管理 | SessionManager 加载/保存 storage_state |
| 指纹管理 | DeviceFingerprintManager 按账号应用指纹 |
| 弹窗处理 | UniversalPopupHandler / guard_overlays |
| 重试与错误报告 | 结构化错误（phase/component/version/url） |

### 禁止行为

- 生成器不得注入"门卫检测"（`_login_element_candidates` + `to_have_count(1)` + `_route_markers`）
- 生成器不得注入"泛化容器发现"（`_form_candidates` 多候选搜索）
- 生成器不得注入"双信号联合判断"（URL 标记 + 元素唯一性联合校验）
- 运行时不得使用 `to_have_count(1)` 作为页面就绪条件（应使用 `.first.wait_for(state="visible")`）

---

## 16. `.first` 使用原则

生成器默认**不添加** `.first`。lint 工具对 `.first/.nth` 的完整要求如下：

| 场景 | 是否允许 `.first` | 必须附带 |
|------|:------------------:|----------|
| `_form = page`（无具体容器） | 禁止 | 应先收敛作用域而非靠 `.first` 掩盖多匹配 |
| `_form = page.locator(...)`（具体容器） | 允许 | 紧邻上方需注释说明业务语义（如 `# 表单内用户名/密码唯一`） |
| 验证码恢复路径 | 禁止 `.first` | 使用 `expect(...).to_have_count(1)` 保证唯一性 |
| 运行时页面就绪检测 | 允许 | 使用 `.first.wait_for(state="visible")` 探测任一匹配即可 |

本节是第 1 节"限制使用 `.first`"和第 13 节"定位器唯一性契约"的具体判定标准。
