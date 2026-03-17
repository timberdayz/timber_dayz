## Why

采集录制生成器（`steps_to_python.py`）生成的 Python 组件代码质量差，几乎不可直接使用，根因有二：

1. **选择器来源质量差**：Inspector JS 注入只检测显式 `role` 属性，不检测隐式角色（button/a/input 等）、placeholder、label，导致大部分元素退化为不稳定的 CSS 选择器
2. **生成器场景覆盖不足**：export 组件无下载模板、不支持 select/press/download 等常见 action、非 login/export 组件不继承正确基类

本次优化目标：让生成器输出"可微调使用"的代码，而非"几乎需要重写"的代码。

## What Changes

### P0：JS 注入增强选择器质量
- 为 `_inject_event_capture_script` 添加 HTML 隐式角色检测（button/a/input/select/h1-h6/nav/textarea 等自动映射为 ARIA role）
- 添加 `placeholder` 属性捕获（input/textarea），优先级仅次于 role
- 添加 `label` 关联捕获（通过 `label[for=id]` 或父级 `<label>` 查找）
- 添加选择器唯一性验证（生成选择器后用 `querySelectorAll` 验证是否唯一匹配，不唯一则标记）

### P1：生成器补全场景模板
- Export 组件生成完整下载模板（`page.expect_download()` + 文件保存 + `build_standard_output_root()`）
- 支持 `select`（下拉框选择）、`press`（键盘操作）、`download`（文件下载）action 的代码生成
- 非 login/export 组件继承正确基类（NavigationComponent / DatePickerComponent）
- 修复 `wait` 步骤生成无意义的 `domcontentloaded`，改为 `networkidle` 或条件等待

### P2：修复已知 Bug
- 修复 `had_captcha_raise` 导致验证码与登录按钮之间的非验证码步骤被丢弃
- 验证码恢复块 URL 判断从 `success_criteria` 配置读取，不硬编码 `/welcome`、`/dashboard`
- 清理 `import os` 重复导入和 `params` 重复定义

## Capabilities

### New Capabilities

_无新增能力，本次为现有能力的质量优化。_

### Modified Capabilities

- `data-collection`: 采集录制生成器的选择器质量和代码生成完整性要求变更（录制 JS 注入选择器策略升级、生成器 action 覆盖范围扩展、组件模板完整性增强）

## Impact

- `tools/launch_inspector_recorder.py` — JS 注入脚本重写（`_inject_event_capture_script`）
- `backend/services/steps_to_python.py` — 生成器核心逻辑扩展（新 action 支持、export 模板、基类继承修复、`_selector_from_selectors` unique 降级逻辑、bug 修复、新增 `success_criteria` 参数）
- `backend/routers/component_recorder.py` — 两处 `generate_python_code` 调用需传递 `success_criteria` 参数
- `backend/tests/test_steps_to_python_regression.py` — 回归测试补充
- `backend/tests/test_component_recorder_lint.py` — lint 规则测试更新
- 不影响已有手写组件、执行器、前端录制页面
