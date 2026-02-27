# Tasks: 采集脚本录制工具产出 Python 组件（规范对齐）

**目标**：录制停止后能生成符合《采集脚本编写规范》的 .py 代码，前端可预览/编辑并保存为 Python 组件；主路径为「录制 → 步骤 → 生成 .py → 保存 .py」。

## 1. 步骤 → Python 代码生成器（后端）

- [ ] 1.1 在 `backend/services/` 或 `backend/utils/` 下新增步骤→Python 生成模块（如 `steps_to_python.py` 或 `collection_recorder_codegen.py`），输入与 `/recorder/stop` 返回的 steps 结构一致（platform、component_type、component_name、steps 列表），输出 Python 源码字符串。
- [ ] 1.2 生成器实现组件契约：生成 `async def run(page, account, config)`（或项目约定的 LoginComponent/ExportComponent 签名）、返回 ResultBase 子类；配置从 ctx/config 读取的注释或占位。
- [ ] 1.3 生成器对 click/fill/navigate/wait 等步骤：在可推断 role/label/text 时优先生成 `get_by_role`/`get_by_label`/`get_by_text`，否则生成 `page.locator(selector)` 并加「建议迁移到 get_by_*」类注释；在 click/fill 前生成 `expect(locator).to_be_visible()` 或 `locator.wait_for(state="visible")`，避免裸 time.sleep。
- [ ] 1.4 生成器对 `optional=true` 的步骤：生成 try/except 或「先判断可见再操作」等可选执行逻辑，或至少注释「可选步骤，执行失败可跳过」，与 YAML optional 行为一致。
- [ ] 1.5 生成器在脚本中按《采集脚本编写规范》留注释占位（如复杂交互、临时弹窗、下载等），便于用户录制后补全；文件头注释注明「以 COLLECTION_SCRIPT_WRITING_GUIDE.md 为准」。

## 2. 录制 API 扩展

- [ ] 2.1 在 `POST /recorder/stop` 的响应中增加 `python_code` 字段：仅当 mode=steps 且存在 steps 时，从 recorder_session 取 platform/component_type、以 component_type 为默认 component_name 调用生成器，将结果放入响应；mode=discovery 时不调用生成器、不返回 python_code（或返回空）；生成器异常或 steps 为空时不返回或返回空，前端可提示「未生成代码，请检查步骤或使用重新生成」。和现有 steps、mode 等一并返回。
- [ ] 2.2 （可选）新增 `POST /recorder/generate-python`：请求体含 platform、component_type、component_name、steps；响应含 `python_code`，供前端「仅重新生成」时使用。

## 3. 前端：Python 预览、编辑与保存

- [ ] 3.1 在录制结果页（ComponentRecorder.vue 或等价）增加「Python 代码」区域：展示 stop 返回的 `python_code`（或调用 generate-python 的结果），支持可编辑文本框或代码高亮组件；若 `python_code` 缺失或为空则提示「未生成代码，请检查步骤或使用重新生成」。停止后用户可输入或确认组件名（component_name），保存时以该名称写入文件。
- [ ] 3.2 保存逻辑：用户点击保存时，将当前展示的 Python 代码（默认或编辑后）作为 `python_code` 与 platform、component_name 等一并提交到 `POST /recorder/save`；不再仅传 yaml_content 作为主路径，主路径为保存 .py。
- [ ] 3.3 保留「步骤列表 / YAML」的展示与可选「导出 YAML」或 YAML 保存（兼容），不删除现有 YAML 相关 UI，仅将「Python 预览 + 保存 .py」设为主流程。

## 4. 文档与验收

- [ ] 4.1 在 `docs/guides/` 或录制相关文档中补充：录制完成后如何查看/编辑生成的 Python 代码、如何按《采集脚本编写规范》微调、保存后组件位置与版本注册说明。
- [ ] 4.2 验收：从前端开始录制 → 停止 → 看到生成的 Python 代码 → 编辑后保存 → 确认 `modules/platforms/{platform}/components/{component_name}.py` 存在且可被执行器加载；生成的代码符合规范中的契约与定位/等待约定（可人工抽查）。
