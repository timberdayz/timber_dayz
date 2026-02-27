# Tasks: 真实采集脚本编写规范

**目标**：规范文档交付后，后续可**按业界主流方式**编写采集脚本；撰写时以提案中的「场景列表与检测/应对概要」「现状与业界对照」为依据，补齐缺口并统一写法。

## 1. 规范文档

- [x] 1.1 在 `docs/guides/` 下新建 `COLLECTION_SCRIPT_WRITING_GUIDE.md`（或与团队约定的路径，如 `docs/DEVELOPMENT_RULES/`）。
- [x] 1.2 文档包含「元素定位」：优先 `get_by_role` / `get_by_label` / `get_by_text`；避免易变 CSS/ID；选择器集中到 `*_config.py` 的说明与示例；多语言/多站点时按钮优先 get_by_role 或配置多语言候选；iframe 内元素先用 frame_locator 或 page.frames 选定再定位；Shadow DOM 注明 Playwright 默认穿透；动态列表/Stale 约定每次再查或带唯一 key，避免长期持有 locator。
- [x] 1.3 文档包含「元素检测与可重试等待」：禁止单次 `count() + is_visible()` 后即操作；应使用 `expect(locator).to_be_visible()` 或 `locator.wait_for(state="visible")`，或直接对 locator 执行 click/hover/fill 以利用 auto-wait；并说明为何单次检测在慢网/动画下易失败。
- [x] 1.4 文档包含「等待策略」：优先自动等待与条件等待（`expect(locator).to_be_visible()`、`wait_for(state="visible")`）；`wait_for_timeout` 仅用于必要人为节奏并注明原因。
- [x] 1.5 文档包含「复杂交互（悬停→内容出现→点击）」：推荐流程 trigger.hover() → 对下拉/菜单 `wait_for(state="visible")` 或 expect；菜单项优先 `get_by_role("menuitem", name="...")`；视需 scroll_into_view_if_needed、item.hover() → item.click()；优先 locator 方法，page.mouse 仅作兜底；避免用固定 timeout 替代「等菜单出现」。
- [x] 1.6 文档包含「组件契约」：与 `ExecutionContext`、`LoginComponent.run(page)`、`ExportComponent.run(page, mode)` 及 `*_config` 的配合；统一返回 `ResultBase` 子类；脚本假定 context 已设置 accept_downloads 与 downloads_path，组件仅用任务目录保存文件。
- [x] 1.7 文档包含「错误与重试」：关键步骤与 `RetryStrategy` 或组件内重试的约定；平台限流/429 时退避重试；page/context 关闭或导航超时时视策略重试或快速失败并明确错误类型；网络/请求失败（接口 5xx、超时、离线）时按策略重试或快速失败并明确错误类型；可选引用 Playwright 官方 Best Practices、Actionability、Locators 与项目内已符合规范的示例。文档可注明「以 Playwright Python 当前文档与 API 为准」，避免 API 升级后歧义。
- [x] 1.8 文档包含「临时弹窗与遮挡层」：执行器在登录前、每域导出前调用 `close_popups` 及平台 popup_config；组件内已知弹窗应显式 wait 再关闭/确认；不可预期弹窗可依赖执行器或说明 `add_locator_handler` 的适用与注意点；Cookie 弹窗需合规选择时显式 wait 接受/拒绝再点击；浏览器权限弹窗可依赖执行器或 handler，需自动选时配置选择器。
- [x] 1.9 文档包含「各场景下如何编写脚本（场景与业界设计）」：列出临时验证码（OTP/图形，含导出阶段同套流程）、临时弹窗（含 Cookie 接受/拒绝）、临时遮罩、Toast、会话过期（含每域前后检查）、加载中/骨架屏、长时间生成/异步导出、下载确认/文件弹窗（含新标签页与下载路径约定）、不可预期遮挡（含 add_locator_handler 仅自包含 click、防死循环、浏览器权限弹窗），以及 iframe 内操作、新标签页、平台限流、页面崩溃/超时等；并包含**现代化网页补充场景**：SPA 路由/导航、虚拟列表/无限滚动、文件上传（input file）、空状态/无数据、多步向导、网络/请求失败、**分页（Pagination）**；对每种说明业界主流的检测方式与应对方式及本项目编写要点；可引用提案中的场景列表与检测/应对概要表。
- [x] 1.10 文档撰写时对照提案「现状与业界对照」表：对表中列出的各缺口在对应小节中给出明确对齐要求，使编写者按业界主流方式落笔。缺口包括：验证码回填 get_by_*、可预期弹窗显式 wait、Modal 用 get_by_role 与条件等待、Toast/会话过期/加载成文约定、禁止 count+is_visible、add_locator_handler（仅自包含 click、防死循环）；**真实采集环境**：iframe 内定位与关闭弹窗、新标签页 expect_event("page") 与 close、下载路径约定、长时间生成条件等待、平台限流检测与退避、页面崩溃/超时与错误类型、多语言/多站点文案、每域前后会话检查、导出阶段验证码与登录同套流程；**现代化网页补充**：Shadow DOM 注明默认穿透、动态列表/Stale 每次再查或唯一 key、Cookie 接受/拒绝显式 wait、SPA 路由等目标页特征、虚拟列表滚动后 wait_for、文件上传 set_input_files、空状态判断非空再操作、权限弹窗与多步向导约定、网络/请求失败与超时区分、**分页点击后等当前页/列表刷新**、**API 与版本注明**。
- [x] 1.11 文档包含「iframe 与交互框/信息框类型及业界检测/应对」：罗列主流 iframe 与交互框类型（同源业务/组件 iframe、跨域登录/支付/广告 iframe、Modal/Dialog、Drawer、Popover/Dropdown），及各类的业界检测方式与应对方式；可引用提案中的「主流 iframe 与交互框/信息框类型」表、「业界检测方式（按类型）」表、「业界应对方式（按类型）」表，便于编写者按类型选用。
- [x] 1.12 文档包含「现代化网页补充场景」：按业界主流写明 Shadow DOM、SPA 路由/导航、虚拟列表/无限滚动、文件上传（input file）、Cookie 接受/拒绝、空状态/无数据、浏览器权限弹窗、多步向导、网络/请求失败、**分页（Pagination）**的检测与应对；可引用提案中场景列表与检测/应对概要表的对应行。文档可注明「以 Playwright Python 当前文档与 API 为准」。

## 2. 文档索引与引用

- [x] 2.1 在 `CLAUDE.md` 或 `docs/DEVELOPMENT_RULES/README.md` 的「开发中参考」中增加对《采集脚本编写规范》的引用，便于 Agent 与新人查阅。

## 3. 规格增量（可选）

- [x] 3.1 若采纳「data-collection 增加规范遵循需求」：在 `openspec/changes/add-collection-script-writing-guide/specs/data-collection/spec.md` 中完成 ADDED 需求与 Scenario，并通过 `openspec validate add-collection-script-writing-guide --strict`。
