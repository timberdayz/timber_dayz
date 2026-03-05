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

## 6. 后续可做（新开对话继续）

- [ ] 6.1 测试路径收敛：删除录制页基于临时 YAML/Python 的「测试组件」按钮及 `/recorder/test` 接口，仅保留组件版本管理中的测试能力作为唯一组件执行入口；如有需要，可在录制页保存成功后提供「前往组件版本管理并测试」的引导（可选，偏 UX）。
- [ ] 6.2 登录成功条件：保存/测试时支持配置 success_criteria（如 url_contains）（可选）。
- [ ] 6.3 步骤标记扩展：导航、弹窗/通知栏等，并约定 YAML/执行器语义（可选）。
- [ ] 6.4 验证码组件：实现 captcha_solver，YAML 中 captcha 标记转为 component_call（可选）。
- [ ] 6.5 文档：RECORDER_PYTHON_OUTPUT.md 补充录制页与组件版本管理的职责边界（仅后者提供测试）、步骤标记与后续优化说明（可选）。
- [ ] 6.6 步骤语义字段：在录制/解析链路中为 steps 增加 `step_type` 与 `scene_tags` 等高层语义字段（如 login_form、cookie_consent、export_wizard_step、otp_dialog、iframe_step），并在 Trace 解析与 Recorder API 中根据 DOM/文案/上下文填充基础场景，供生成器选择场景模板使用（可选，偏后端）。
- [ ] 6.7 生成器场景模板与抗干扰集成：基于 `step_type` / `scene_tags` 实现登录表单、业务 Modal 关闭、导出向导步骤等「场景模板」，并在登录/导出等关键节点自动插入 `await self.guard_overlays(page, label="...")`；对已识别的可预期弹窗/遮挡，优先生成显式 wait+关闭/确认逻辑或调用平台弹窗 helper，而非仅依赖全局 close_popups（可选，偏后端）。
- [ ] 6.8 生成后质量检查与前端提示：在 `/recorder/stop` 或 `/recorder/generate-python` 中对生成的 `python_code` 执行语法检查（如 `py_compile`）及轻量 Lint 子集，将语法错误与不推荐模式（如裸 `wait_for_timeout`）汇总为结构化的错误/警告列表返回；前端在录制结果页展示「质量提示」（数量 + 列表），辅助脚本作者快速修正生成结果（可选，后端+前端联动）。
