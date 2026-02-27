# 数据采集能力 - 录制工具产出 Python 组件变更增量

## ADDED Requirements

### Requirement: 采集组件录制工具 SHALL 产出符合《采集脚本编写规范》的 Python 组件（.py）

系统 SHALL 在用户通过前端完成采集组件录制（Inspector + Trace）后，能够生成符合项目《采集脚本编写规范》的 Python 源码，并支持在前端预览、编辑后保存为 `modules/platforms/{platform}/components/{component_name}.py`，供执行器直接加载运行。录制工具的主产出为 .py 文件，与现有 Python 组件契约一致。

#### Scenario: 录制停止后返回生成的 Python 代码

- **WHEN** 用户在前端点击「停止录制」且录制会话已产生步骤（steps）
- **THEN** 后端 SHALL 使用「步骤→Python 代码生成器」将 steps 转换为 Python 源码字符串
- **AND** 后端 SHALL 在停止录制的响应中返回 `python_code` 字段（或通过单独的「生成 Python」接口返回），供前端展示与编辑
- **AND** 生成的代码 SHALL 符合《采集脚本编写规范》中的组件契约（如 async def run(page, account, config)、ResultBase 子类）、定位优先 get_by_*、显式条件等待（expect/wait_for），并包含规范相关注释占位

#### Scenario: 前端可预览并编辑生成的 Python 后保存为 .py

- **WHEN** 用户在前端录制结果页查看生成的 Python 代码
- **THEN** 前端 SHALL 提供 Python 代码的展示与可编辑区域（文本框或代码高亮组件）
- **AND** 用户点击保存时，前端 SHALL 将当前 Python 代码（默认生成或用户编辑后）作为 `python_code` 与 platform、component_name 等一并提交到 `POST /recorder/save`
- **AND** 后端 SHALL 将 python_code 写入 `modules/platforms/{platform}/components/{component_name}.py` 并完成版本注册，使该组件可被执行器加载

#### Scenario: 步骤→Python 生成器输出符合规范

- **WHEN** 步骤→Python 代码生成器根据 platform、component_type、component_name 与 steps 列表生成 Python 源码
- **THEN** 生成器 SHALL 在可推断 role/label/text 时优先生成 `page.get_by_role()`、`get_by_label()`、`get_by_text()`，否则生成 `page.locator(selector)` 并加注释建议迁移到 get_by_*
- **AND** 生成器 SHALL 在 click/fill 等操作前生成 `expect(locator).to_be_visible()` 或 `locator.wait_for(state="visible")`，避免裸的 time.sleep
- **AND** 生成器 SHALL 在脚本中按《采集脚本编写规范》留注释占位（如复杂交互、临时弹窗、下载等），并在文件头注明以 COLLECTION_SCRIPT_WRITING_GUIDE.md 为准
