# Tasks: 采集脚本录制工具产出 Python 组件（规范对齐）

**目标**：录制停止后能生成符合《采集脚本编写规范》的 .py 代码，前端可预览/编辑并保存为 Python 组件；主路径为「录制 → 步骤 → 生成 .py → 保存 .py」。

## 1. 步骤 → Python 代码生成器（后端）

- [x] 1.1 在 `backend/services/` 或 `backend/utils/` 下新增步骤→Python 生成模块（如 `steps_to_python.py` 或 `collection_recorder_codegen.py`），输入与 `/recorder/stop` 返回的 steps 结构一致（platform、component_type、component_name、steps 列表），输出 Python 源码字符串。
- [x] 1.2 生成器实现组件契约：生成 `async def run(page, account, config)`（或项目约定的 LoginComponent/ExportComponent 签名）、返回 ResultBase 子类；配置从 ctx/config 读取的注释或占位。
- [x] 1.3 生成器对 click/fill/navigate/wait 等步骤：在可推断 role/label/text 时优先生成 `get_by_role`/`get_by_label`/`get_by_text`，否则生成 `page.locator(selector)` 并加「建议迁移到 get_by_*」类注释；在 click/fill 前生成 `expect(locator).to_be_visible()` 或 `locator.wait_for(state="visible")`，避免裸 time.sleep。
- [x] 1.4 生成器对 `optional=true` 的步骤：生成 try/except 或「先判断可见再操作」等可选执行逻辑，或至少注释「可选步骤，执行失败可跳过」，与 YAML optional 行为一致。
- [x] 1.5 生成器在脚本中按《采集脚本编写规范》留注释占位（如复杂交互、临时弹窗、下载等），便于用户录制后补全；文件头注释注明「以 COLLECTION_SCRIPT_WRITING_GUIDE.md 为准」。

## 2. 录制 API 扩展

- [x] 2.1 在 `POST /recorder/stop` 的响应中增加 `python_code` 字段：仅当 mode=steps 且存在 steps 时，从 recorder_session 取 platform/component_type、以 component_type 为默认 component_name 调用生成器，将结果放入响应；mode=discovery 时不调用生成器、不返回 python_code（或返回空）；生成器异常或 steps 为空时不返回或返回空，前端可提示「未生成代码，请检查步骤或使用重新生成」。和现有 steps、mode 等一并返回。
- [x] 2.2 （可选）新增 `POST /recorder/generate-python`：请求体含 platform、component_type、component_name、steps；响应含 `python_code`，供前端「仅重新生成」时使用。

## 3. 前端：Python 预览、编辑与保存

- [x] 3.1 在录制结果页（ComponentRecorder.vue 或等价）增加「Python 代码」区域：展示 stop 返回的 `python_code`（或调用 generate-python 的结果），支持可编辑文本框或代码高亮组件；若 `python_code` 缺失或为空则提示「未生成代码，请检查步骤或使用重新生成」。停止后用户可输入或确认组件名（component_name），保存时以该名称写入文件。
- [x] 3.2 保存逻辑：用户点击保存时，将当前展示的 Python 代码（默认或编辑后）作为 `python_code` 与 platform、component_name 等一并提交到 `POST /recorder/save`；不再仅传 yaml_content 作为主路径，主路径为保存 .py。
- [x] 3.3 保留「步骤列表 / YAML」的展示与可选「导出 YAML」或 YAML 保存（兼容），不删除现有 YAML 相关 UI，仅将「Python 预览 + 保存 .py」设为主流程。

## 4. 文档与验收

- [x] 4.1 在 `docs/guides/` 或录制相关文档中补充：录制完成后如何查看/编辑生成的 Python 代码、如何按《采集脚本编写规范》微调、保存后组件位置与版本注册说明。
- [x] 4.2 验收：从前端开始录制 → 停止 → 看到生成的 Python 代码 → 编辑后保存 → 确认 `modules/platforms/{platform}/components/{component_name}.py` 存在且可被执行器加载；生成的代码符合规范中的契约与定位/等待约定（可人工抽查）。

## 5. 录制与解析优化（已实施）

- [x] 5.1 Trace 解析：仅处理 action 事件（方案 A），不处理 before/after；新增 500ms 时间窗 (action_type, selector, value) 去重（方案 C）。`backend/utils/trace_parser.py`
- [x] 5.2 生成器：从 step.selectors 推导 selector，使 Inspector 步骤能生成可执行 locator/click/fill。`backend/services/steps_to_python.py`
- [x] 5.3 生成器：navigate/goto 后插入 wait_for_load_state。`backend/services/steps_to_python.py`
- [x] 5.4 Inspector：最近 2～3 步同 action+主 selector 去重。`tools/launch_inspector_recorder.py`
- [x] 5.5 测试组件：登录步骤 value 自动替换为 {{account.username}}/{{account.password}}；验证码相关步骤自动 optional。`backend/routers/component_recorder.py`
- [x] 5.6 前端：新增「标记为验证码」；步骤工具条 sticky 固定，仅步骤列表滚动。`frontend/src/views/ComponentRecorder.vue`

## 6. 后续可做（本次对话已实施）

- [x] 6.1 测试路径收敛：删除录制页「测试组件」按钮及 `/recorder/test` 接口，仅保留组件版本管理中的测试能力；录制页保存成功后提供「前往组件版本管理并测试」的引导。`backend/routers/component_recorder.py`、`frontend/src/views/ComponentRecorder.vue`
- [x] 6.2 登录成功条件：保存时支持配置 success_criteria（url_contains），写入组件内校验逻辑。`RecorderSaveRequest.success_criteria`、save 时注入代码、前端「登录成功条件」输入。
- [x] 6.3 步骤标记扩展：前端增加「导航」「弹窗/通知栏」标记选项，约定语义（见 RECORDER_PYTHON_OUTPUT.md §7）。`ComponentRecorder.vue`
- [x] 6.4 验证码组件：captcha 标记保留，测试时视为可选；文档说明预留后续 captcha_solver/component_call。未实现完整 solver，仅语义与文档。
- [x] 6.5 文档：RECORDER_PYTHON_OUTPUT.md 补充录制页与组件版本管理职责边界、步骤标记含义与后续优化说明。`docs/guides/RECORDER_PYTHON_OUTPUT.md`
- [x] 6.6 步骤语义字段：在 Recorder API 中根据 step_group 填充 `step_type` / `scene_tags`（navigation、popup、date_picker、filters、captcha 等）。`_enrich_steps_semantics()`、stop 与 generate-python 调用。
- [x] 6.7 生成器场景模板与抗干扰：对「弹窗/通知栏」步骤生成可选 wait dialog + 点击确定/关闭；登录/导出关键节点已插入 guard_overlays。`backend/services/steps_to_python.py`
- [x] 6.8 生成后质量检查与前端提示：stop 与 generate-python 返回 lint_errors/lint_warnings；前端展示语法错误与规范建议。已实施。

## 7. 待实施：验证码类型与测试阶段回传（见 proposal §10）（已实施）

- [x] 7.1 **验证码类型区分（录制器）**：前端步骤标记将「验证码」拆为「图形验证码」（需截图给用户看后输入）与「短信/OTP 验证码」（用户查收后输入，无需截图）；`_enrich_steps_semantics` 中为 step_group 补充 scene_tags（如 graphical_captcha / otp），与《COLLECTION_LOGIN_VERIFICATION》的 verification_type 一致；**向后兼容**：保留对 step_group=captcha 的识别，未区分子类型时视为 graphical_captcha 或 scene_tags 保留 captcha；文档（RECORDER_PYTHON_OUTPUT.md 或采集规范）说明两种类型的含义与用法。
- [x] 7.2 **测试阶段验证码暂停与回传（子进程）**：子进程在执行 `adapter.login(page)` 时捕获 `VerificationRequiredError`；不关浏览器、不立即失败；将 verification 相关字段**合并**写入现有 `progress.json`（保留 progress、current_step 等），写入 `status: "verification_required"`、`verification_type`、`verification_screenshot`（test_dir 内路径）；轮询 `temp/component_tests/{test_id}/verification_response.json`（超时约 5 分钟）；超时则关闭浏览器、status=failed，并在 progress/result 中写 `verification_timeout: true` 或 error 含「验证码输入超时」；读到回传则在当前 page 填入验证码并继续（手写组件可带 params.captcha_code 再执行 login；录制组件由测试工具代为 fill + click）。
- [x] 7.3 **测试阶段验证码回传（后端）**：完整路径为 `GET/POST /component-versions/{version_id}/test/{test_id}/...`（version_id 必选）。`GET .../status` 在 progress 为 verification_required 时返回 verification_type、**verification_screenshot_url**（指向 GET verification-screenshot 的 URL）；新增 `GET .../verification-screenshot` 读 test_dir 内截图返回图片流；新增 `POST .../resume`，请求体 `captcha_code` 或 `otp`，**校验** test 存在且 status 为 verification_required 且当前用户对该 version/test 有权限，否则 4xx；超时或测试已结束后再调用 resume 返回 4xx；通过后写入 `temp/component_tests/{test_id}/verification_response.json`。
- [x] 7.4 **测试阶段验证码回传（前端）**：轮询 status 发现 `verification_required` 时，按 verification_type 展示「图形验证码」则用 **verification_screenshot_url** 请求并显示截图 + 输入框、「短信/OTP」则仅输入框；用户提交后调用 `POST .../resume`；继续轮询直至测试完成。

## 8. 验证码流程加固（已实施）

- [x] 8.1 **MiaoshouLogin 修复**：将「若有回传的验证码/OTP」块移至 `run()` 开头、`page.goto` 之前，避免重试时刷新页面导致需重新输入账号密码。`modules/platforms/miaoshou/components/login.py`
- [x] 8.2 **生成器验证码感知**：登录组件含验证码步骤（step_group 为 captcha/captcha_graphical/captcha_otp 或 scene_tags 含 graphical_captcha/otp）时，生成恢复路径（params.captcha_code 时同页填入并点击）、验证码步骤改为检测 DOM → 截图 → raise VerificationRequiredError。`backend/services/steps_to_python.py`
- [x] 8.3 **文档**：RECORDER_PYTHON_OUTPUT.md 补充生成器验证码感知与手写组件约定（恢复块须在 page.goto 之前）。

## 9. 登录与步骤完成度检测（对应 proposal §10.4）

- [x] 9.1 **统一登录成功检测 helper**：在登录组件模板或生成器中实现统一的登录结果检测函数/代码块，基于 `success_criteria`（至少支持 `url_contains` / `url_not_contains` / `element_visible`），在组件末尾调用并据此返回 `LoginResult(success=..., message=...)`，不再在各处手写零散的 `if "/welcome" in url` 判断。已在 `backend/routers/component_recorder.py` 中实现 `_inject_login_success_criteria_block` 并在保存登录组件时自动注入。
- [x] 9.2 **验证码恢复路径与主流程对齐**：更新生成器的登录验证码恢复块，使其在填入验证码并点击登录后，调用与主流程相同或等价的登录成功检测逻辑；无论检测成功或失败，恢复块均必须立即 `return`，避免继续执行下方主流程再次触发验证码。生成器与 `miaoshou_login` 组件已保证恢复路径在成功与失败时均直接返回。
- [x] 9.3 **导航/导出步骤级检测模板**：在生成器中为 navigation / export 等组件类型补充通用的「步骤完成度检测」模板：导航步骤在 `goto` 或菜单点击后已统一插入 `wait_for_load_state` 与 `guard_overlays`；导出组件在模板中保留「等待下载或确认文件路径」的注释占位，后续可结合 success_criteria 扩展；本次变更不新增代码分支，仅在规范与文档中确认现有模板为推荐做法。
- [x] 9.4 **文档与示例更新**：在 `RECORDER_PYTHON_OUTPUT.md` 中补充登录场景的 `success_criteria` 字段说明与 JSON 示例（含 `url_contains` / `url_not_contains` / `element_visible_selector`），并在 COMPONENT_RECORDING_GUIDE 等文档中保留导航/导出 success_criteria YAML 示例，指导录制时按真实站点行为配置检测条件。
- [x] 9.5 **回归与测试**：新增 `tests/test_login_success_criteria_injection.py`，覆盖 `success_criteria` 注入逻辑：验证 url_contains / url_not_contains / element_visible_selector 会正确生成检测代码块、移除默认 TODO 且在无占位块时保持代码不变；结合已有验证码恢复路径修复，保证单次执行内不会重复整段登录步骤。
