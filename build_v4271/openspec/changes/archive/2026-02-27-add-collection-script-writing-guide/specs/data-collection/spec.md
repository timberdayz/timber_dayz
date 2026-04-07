## ADDED Requirements

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
