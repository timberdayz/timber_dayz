## MODIFIED Requirements

### Requirement: 采集组件录制工具 SHALL 产出符合《采集脚本编写规范》的 Python 组件（.py）

系统 SHALL 在用户通过前端完成采集组件录制（Inspector + Trace）后，能够生成符合项目《采集脚本编写规范》的 Python 源码，并支持在前端预览、编辑后保存为 `modules/platforms/{platform}/components/{component_name}.py`，供执行器直接加载运行。录制工具的主产出为 .py 文件，与现有 Python 组件契约一致。**生成器 SHALL 仅输出用户录制步骤的忠实回放代码与必要的组件元数据/导航/验证码处理，不得注入运行时框架逻辑（如页面就绪检测、泛化容器搜索等）。**

#### Scenario: 录制停止后返回生成的 Python 代码

- **WHEN** 用户在前端点击"停止录制"且录制会话已产生步骤（steps）
- **THEN** 后端 SHALL 使用"步骤转 Python 代码生成器"将 steps 转换为 Python 源码字符串
- **AND** 后端 SHALL 在停止录制的响应中返回 `python_code` 字段（或通过单独的"生成 Python"接口返回），供前端展示与编辑
- **AND** 生成的代码 SHALL 符合《采集脚本编写规范》中的组件契约（如 async def run(page, account, config)、ResultBase 子类）、定位优先 get_by_*、显式条件等待（expect/wait_for），并包含规范相关注释占位

#### Scenario: 前端可预览并编辑生成的 Python 后保存为 .py

- **WHEN** 用户在前端录制结果页查看生成的 Python 代码
- **THEN** 前端 SHALL 提供 Python 代码的展示与可编辑区域（文本框或代码高亮组件）
- **AND** 用户点击保存时，前端 SHALL 将当前 Python 代码（默认生成或用户编辑后）作为 `python_code` 与 platform、component_name 等一并提交到 `POST /recorder/save`
- **AND** 后端 SHALL 将 python_code 写入 `modules/platforms/{platform}/components/{component_name}.py` 并完成版本注册，使该组件可被执行器加载

#### Scenario: 步骤转 Python 生成器输出符合规范

- **WHEN** 步骤转 Python 代码生成器根据 platform、component_type、component_name 与 steps 列表生成 Python 源码
- **THEN** 生成器 SHALL 在可推断 role/label/text 时优先生成 `page.get_by_role()`、`get_by_label()`、`get_by_text()`，否则生成 `page.locator(selector)` 并加注释建议迁移到 get_by_*
- **AND** 生成器 SHALL 在 click/fill 等操作前生成 `expect(locator).to_be_visible()` 或 `locator.wait_for(state="visible")`，避免裸的 time.sleep
- **AND** 生成器 SHALL 在脚本中按《采集脚本编写规范》留注释占位（如复杂交互、临时弹窗、下载等），并在文件头注明以 COLLECTION_SCRIPT_WRITING_GUIDE.md 为准

#### Scenario: login 组件生成器不注入运行时框架逻辑

- **WHEN** 生成器为 login 类型组件生成代码
- **THEN** 生成器 SHALL NOT 注入"门卫检测"逻辑（如 `_login_element_candidates` 循环 + `to_have_count(1)` + `_route_markers` URL 检测）
- **AND** 生成器 SHALL NOT 注入"泛化容器发现"逻辑（如 `_form_candidates` 多候选搜索 + `to_have_count(1)` 唯一性断言）
- **AND** 生成器 SHALL 保留 URL 导航逻辑（`_target_url` 来源优先级 + `page.goto`），因为这是 login 组件的核心业务需求
- **AND** 生成器 SHALL 保留验证码检测与 `VerificationRequiredError` 暂停逻辑
- **AND** 生成器 SHALL 在录制步骤包含明确容器信息时（如步骤在特定 form/dialog 内），生成具体的容器 locator（如 `_form = page.locator("#J_loginRegisterForm")`），而非泛化搜索

#### Scenario: login 组件生成器注入登录成功条件模板

- **WHEN** 生成器为 login 类型组件生成代码且步骤中未显式包含成功判断
- **THEN** 生成器 SHALL 在步骤回放后注入登录成功条件的模板代码（如 URL 变化检测 + 关键元素检查），并以 TODO 注释标注需用户根据实际平台编辑完善
- **AND** 模板 SHALL 使用 `page.wait_for_url` 或 URL 模式匹配作为主判断方式，而非 `_route_markers` 硬编码列表

## ADDED Requirements

### Requirement: 运行时/测试框架层页面就绪检测

系统 SHALL 在运行时层（测试框架和执行器）执行 login 组件前提供页面就绪检测，替代原先注入组件代码中的"门卫检测"逻辑。检测 SHALL 使用"至少一个可见"语义（`.first.wait_for(state="visible")`）而非"严格唯一"语义（`to_have_count(1)`），以兼容真实页面中的多元素场景。

#### Scenario: 测试框架执行 login 组件前检测页面就绪

- **WHEN** `test_component.py` 的测试流程在执行 login 组件的 `run()` 方法前
- **THEN** 系统 SHALL 等待登录页关键元素（如 `input[type='password']`）至少有一个可见（使用 `.first.wait_for(state="visible", timeout=15000)`）
- **AND** 若等待超时，系统 SHALL 返回结构化错误信息（含 `phase=page_readiness`、`current_url`、`target_url`、`timeout`、候选元素状态），而非将失败透传为组件执行错误
- **AND** 系统 SHALL NOT 使用 `to_have_count(1)` 作为就绪检测条件

#### Scenario: 执行器调用 login 组件前的页面稳定

- **WHEN** `executor_v2.py` 在调用 login 组件的 `run()` 方法前
- **THEN** 系统 SHALL 确保已完成 URL 导航和页面基础加载（`domcontentloaded`），并通过弹窗处理清理干扰元素
- **AND** 系统 SHALL NOT 在执行器层注入基于 `to_have_count(1)` 的元素唯一性检测

#### Scenario: 页面就绪检测失败的可观测性

- **WHEN** 页面就绪检测超时（登录页关键元素在指定时间内未可见）
- **THEN** 系统 SHALL 返回包含以下字段的结构化错误：`phase`（"page_readiness"）、`current_url`、`target_url`、`candidates`（候选元素选择器及其状态）、`timeout_ms`
- **AND** 前端 SHALL 在测试失败弹窗中展示"页面就绪检测失败"而非泛化的"组件执行失败"
