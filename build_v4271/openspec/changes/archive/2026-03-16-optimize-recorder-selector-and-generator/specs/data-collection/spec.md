## MODIFIED Requirements

### Requirement: Inspector API 录制模式（2025-12-23 新增）

系统 SHALL 仅支持使用 Playwright Inspector API 进行组件录制，提供持久化会话、固定指纹和 Trace 录制功能。Codegen 模式已废弃。录制过程中的 JS 事件捕获 SHALL 生成高质量选择器，优先使用语义化选择器（role/placeholder/label/text），CSS 选择器仅作为兜底。

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

#### Scenario: JS 事件捕获生成语义化选择器

- **WHEN** 用户在 Inspector 模式中操作页面元素（click、fill、select 等）
- **THEN** JS 注入脚本 SHALL 检测元素的隐式 ARIA 角色（button/link/textbox/checkbox/radio/combobox/heading/navigation/img 等），不仅检测显式 `role` 属性
- **AND** 对于 input/textarea 元素，JS SHALL 捕获 `placeholder` 属性作为选择器候选
- **AND** 对于有关联 `<label>` 的表单元素，JS SHALL 捕获 label 文本作为选择器候选
- **AND** 选择器优先级 SHALL 为：role > placeholder > label > text > css
- **AND** 每个生成的选择器 SHALL 标记唯一性：对 CSS/属性类选择器使用 `querySelectorAll` 验证；对 role 类选择器使用标签+文本组合查询验证（如 `querySelectorAll('button')` 后按 innerText 过滤）；对 placeholder 选择器使用 `querySelectorAll('[placeholder="..."]')` 验证
- **AND** Python 侧 `_selector_from_selectors` SHALL 优先选取标记为 `unique: true` 的选择器；若最高优先级选择器非唯一，SHALL 降级到下一个唯一选择器，并在生成代码中附加注释提醒人工检查

### Requirement: 采集组件录制工具 SHALL 产出符合《采集脚本编写规范》的 Python 组件（.py）

系统 SHALL 在用户通过前端完成采集组件录制（Inspector + Trace）后，能够生成符合项目《采集脚本编写规范》的 Python 源码，并支持在前端预览、编辑后保存为 `modules/platforms/{platform}/components/{component_name}.py`，供执行器直接加载运行。录制工具的主产出为 .py 文件，与现有 Python 组件契约一致。

#### Scenario: 录制停止后返回生成的 Python 代码

- **WHEN** 用户在前端点击「停止录制」且录制会话已产生步骤（steps）
- **THEN** 后端 SHALL 使用「步骤->Python 代码生成器」将 steps 转换为 Python 源码字符串
- **AND** 后端 SHALL 在停止录制的响应中返回 `python_code` 字段，供前端展示与编辑
- **AND** 生成的代码 SHALL 符合《采集脚本编写规范》中的组件契约

#### Scenario: 步骤->Python 生成器输出符合规范

- **WHEN** 步骤->Python 代码生成器根据 platform、component_type、component_name 与 steps 列表生成 Python 源码
- **THEN** 生成器 SHALL 在可推断 role/label/placeholder/text 时优先生成 `page.get_by_role()`、`get_by_label()`、`get_by_placeholder()`、`get_by_text()`，否则生成 `page.locator(selector)` 并加注释建议迁移
- **AND** 生成器 SHALL 在 click/fill 等操作前生成 `expect(locator).to_be_visible()` 或 `locator.wait_for(state="visible")`
- **AND** 生成器 SHALL 支持 click、fill、navigate、wait、select、press、download 七种 action 的代码生成
- **AND** 对于 `select` action，生成器 SHALL 生成 `page.select_option()` 或 `locator.select_option()` 调用
- **AND** 对于 `press` action，生成器 SHALL 生成 `page.keyboard.press()` 或 `locator.press()` 调用
- **AND** 对于 `download` action，生成器 SHALL 生成 `async with page.expect_download()` 下载处理模板

#### Scenario: Export 组件生成完整下载模板

- **WHEN** 生成器为 component_type=export 的组件生成 Python 源码
- **THEN** 生成的 `run()` 方法 SHALL 包含 `async with page.expect_download() as download_info` 下载处理逻辑
- **AND** 生成的代码 SHALL 包含 `build_standard_output_root()` 输出路径计算调用
- **AND** 生成的代码 SHALL 包含 `download.value.save_as(file_path)` 文件保存逻辑
- **AND** 生成的代码 SHALL 返回 `ExportResult(success=True, file_path=file_path)`，file_path 为实际保存路径而非 None

#### Scenario: 非 login/export 组件继承正确基类

- **WHEN** 生成器为 navigation 类型组件生成代码
- **THEN** 生成的类 SHALL 继承 `NavigationComponent`
- **AND** 生成的 `run()` 方法签名 SHALL 为 `async def run(self, page, target: TargetPage) -> NavigationResult`（与基类一致，target 为必选参数）
- **AND** 生成的代码 SHALL import `TargetPage` 枚举

- **WHEN** 生成器为 date_picker 类型组件生成代码
- **THEN** 生成的类 SHALL 继承 `DatePickerComponent`
- **AND** 生成的 `run()` 方法签名 SHALL 为 `async def run(self, page, option: DateOption) -> DatePickResult`（与基类一致，option 为必选参数）
- **AND** 生成的代码 SHALL import `DateOption` 枚举

- **WHEN** 生成器为其他未知类型组件生成代码
- **THEN** 生成的类 SHALL 继承 `ComponentBase`

#### Scenario: Wait 步骤生成有效等待代码

- **WHEN** 步骤列表中包含 wait action 且无显式 `fixed_wait_reason`
- **THEN** 生成器 SHALL 生成 `await page.wait_for_load_state("networkidle", timeout=...)` 而非 `domcontentloaded`
- **AND** 生成器 SHALL 附带注释建议使用 `expect(locator).to_be_visible()` 条件等待

#### Scenario: 验证码后非验证码步骤不丢失

- **WHEN** 步骤列表中验证码 fill 步骤之后还有非验证码步骤（如勾选框、额外点击）
- **THEN** 生成器 SHALL 将验证码 fill 与 raise 之间的非验证码步骤保留生成，放置在 raise 之前，并标注 `# 以下步骤在首次执行时运行（验证码暂停前）`
- **AND** 生成器 SHALL 仅在验证码 fill 步骤处 raise VerificationRequiredError，不跳过后续非验证码步骤
- **AND** 生成器 SHALL 在注释中提醒：步骤顺序可能与录制顺序不同，若步骤依赖验证码区域已出现，需人工调整

#### Scenario: 验证码恢复块 URL 判断可配置

- **WHEN** 登录组件包含验证码步骤且有 success_criteria 配置
- **THEN** `generate_python_code` SHALL 接受可选参数 `success_criteria: Optional[Dict]`
- **AND** 生成器 SHALL 从 success_criteria 中读取 url_contains / url_not_contains 条件生成 URL 判断逻辑
- **AND** 生成器 SHALL 不硬编码 `/welcome`、`/dashboard` 等特定路径
- **AND** `backend/routers/component_recorder.py` 中调用 `generate_python_code` 的两处 SHALL 传递 success_criteria 参数（若可用）
