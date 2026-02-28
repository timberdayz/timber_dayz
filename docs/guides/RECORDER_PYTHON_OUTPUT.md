# 录制工具 Python 产出使用说明

录制停止后，系统会根据步骤自动生成符合《采集脚本编写规范》的 Python 组件代码，并支持在前端预览、编辑后保存为 `.py` 文件。本文说明如何查看/编辑生成的 Python、如何按规范微调、以及保存后组件路径与版本注册。

**相关规范**：`docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md`。

---

## 1. 查看与编辑生成的 Python 代码

1. **开始录制**：在「组件录制」页选择平台与组件类型（登录/导出等），点击「开始录制」；在 Inspector 中完成操作后点击「停止录制」。
2. **步骤模式**：若为步骤模式且录到步骤，停止后会在「YAML 预览」下方出现 **「Python 代码」** 区域，展示后端根据步骤生成的 Python 源码。
3. **未生成时**：若区域为空或提示「未生成代码」，可点击 **「重新生成」** 按钮（会调用 `POST /recorder/generate-python`）；若仍无代码，请检查步骤是否有效（如至少包含 navigate/click/fill 等）。
4. **编辑**：文本框支持直接编辑。可按《采集脚本编写规范》微调：
   - 将 `page.locator(selector)` 改为 `get_by_role` / `get_by_label` / `get_by_text` 等更稳定的定位；
   - 补充弹窗、复杂交互、下载等处的注释或实现；
   - 调整 `expect(locator).to_be_visible()` 或超时等等待逻辑。

---

## 2. 保存为 .py（主路径）

1. **组件名称**：停止录制后「组件名称」可编辑；导出类建议填写如 `orders_export` 等，以便与执行器约定一致。
2. **保存**：点击「保存」时，若 **Python 代码** 区域有内容，会以 **主路径** 将当前内容作为 `python_code` 提交到 `POST /recorder/save`，后端会写入 `modules/platforms/{platform}/components/{component_name}.py`。
3. **无 Python 时**：若未编辑生成代码或未生成，保存会回退为提交 YAML（`yaml_content`），写入 `config/collection_components/{platform}/{component_name}.yaml`，此为兼容路径。

---

## 3. 保存后组件位置与版本

- **Python 组件**：保存至 `modules/platforms/{platform}/components/{component_name}.py`，按平台与组件名分层；代码进入仓库。
- **版本注册**：保存时同时写入 **component_versions** 表（版本号、file_path、is_stable、is_active 等），用于版本选择与统计。
- **调用方式**：主执行路径通过 Python 适配器按 `platform` + `component_name` 动态 import 对应 `.py` 模块。
- **覆盖更新**：同一 `component_name` 再次保存会覆盖同路径文件；若 component_versions 中已有该 file_path，则只更新同一条版本记录的 description/updated_at，不新建版本行。若需历史与回滚，请依赖 Git 对 `modules/platforms/.../components/*.py` 的版本管理。
- **淘汰**：在 component_versions 中将某版本设为 `is_active=False` 可从版本池淘汰；若需彻底不再执行某 Python 组件，需移走或删除对应 `modules/platforms/{platform}/components/{component_name}.py`。

---

## 4. 验收要点

- 从前端：开始录制 → 停止 → 在「Python 代码」区域看到并可编辑生成的代码 → 保存。
- 确认磁盘上存在 `modules/platforms/{platform}/components/{component_name}.py`，且可被执行器加载（无语法错误、符合组件契约）。
- 生成代码具备：组件契约（`async def run(...)`、返回 ResultBase 子类）、get_by_* 优先、click/fill 前 `expect(...).to_be_visible()` 等（可人工抽查或小脚本检查）。
