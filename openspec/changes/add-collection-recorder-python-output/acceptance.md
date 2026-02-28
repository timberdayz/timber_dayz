# 验收：采集脚本录制工具产出 Python 组件

## 验收步骤

1. **前端录制 → 停止 → 看到 Python 代码**
   - 打开「组件录制」页，选择平台与组件类型（如导出），点击「开始录制」。
   - 在 Inspector 中执行若干步骤（如 navigate、click、fill），点击「停止录制」。
   - 确认「步骤列表」有步骤，且下方出现「Python 代码」区域并展示生成的代码；若为空，点击「重新生成」应能生成代码。

2. **编辑与保存为 .py**
   - 在「Python 代码」文本框中做任意编辑（或保持原样）；「组件名称」可修改（如改为 `orders_export`）。
   - 点击「保存」，确认提示保存成功及版本号。

3. **磁盘与可加载性**
   - 确认文件存在：`modules/platforms/{platform}/components/{component_name}.py`（路径中的 platform/component_name 与表单一致）。
   - 打开该 .py 文件，确认无语法错误；可执行：`python -c "import ast; ast.parse(open('modules/platforms/.../components/xxx.py').read())"` 校验语法。

4. **规范符合性（人工抽查）**
   - 生成代码应含：`async def run(...)`、返回 ResultBase 子类、get_by_* 或 locator、click/fill 前有 `expect(...).to_be_visible()` 或类似等待；文件头注释引用 COLLECTION_SCRIPT_WRITING_GUIDE.md。详见 `docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md` 与 `docs/guides/RECORDER_PYTHON_OUTPUT.md`。

## 通过标准

- 上述 1～3 全部通过，4 抽查无严重偏离即视为验收通过。
