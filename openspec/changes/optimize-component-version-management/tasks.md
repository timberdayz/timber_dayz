# Tasks: 组件版本管理优化

**目标**：修复「测试 A 执行 B」、放宽删除规则、验证码步骤必选暂停，并可选增强版本管理体验。

## 1. 测试执行使用选中组件（P0）

- [ ] 1.1 适配器支持「指定组件类」：在 `PythonComponentAdapter` 或 `create_adapter` 中增加可选参数（如 `override_login_class`、`override_navigation_class`、`override_export_class` 等），当提供时，`login()` / `navigate()` / `export()` 使用注入类实例执行，而非 `_load_component_class("login")` 等按模块名加载。**所有 component_type 分支**（login、navigation、export、date_picker）均须支持注入，避免测试 `miaoshou_custom_navigation` 等非标准命名组件时仍执行 `navigation.py`。
- [ ] 1.2 测试工具传入组件类：在 `tools/test_component.py` 的 `_test_python_component_with_browser` 中，将已加载的 `component_class` 传入适配器（或直接使用该类执行），按 component_type 注入对应 override，确保执行的是 `version.file_path` 对应的实现。
- [ ] 1.3 **验证码恢复路径**：`_run_login_with_verification_support` 在用户回传验证码后二次调用 `adapter.login(page)` 时，**必须同样使用注入的 component_class**，不得回退到 `_load_component_class("login")`。否则验证码填入后仍会执行 `login.py` 而非 `miaoshou_login.py`。
- [ ] 1.4 回归：对 `miaoshou_login` 与 `login` 并存场景，在版本管理页分别测试两版本（含验证码回传流程），验证首次执行与回传后二次执行均使用对应文件中的组件。

## 2. 验证码步骤无条件暂停（P0）

- [ ] 2.1 生成器修改：在 `backend/services/steps_to_python.py` 中，对标记为图形验证码的步骤（step_group 或 scene_tags 为 captcha/captcha_graphical/graphical_captcha），生成「到达即截图并 raise」的代码块，移除 `if await _cap_inp.count() > 0`、`is_visible()` 判断及 `except Exception: pass`；使用固定短等待（如 1s）后直接截图并 `raise VerificationRequiredError("graphical_captcha", screenshot_path)`。
- [ ] 2.2 已存在的登录组件：对 `modules/platforms/miaoshou/components/miaoshou_login.py` 中验证码块改为无条件截图与 raise（或通过重新生成/保存刷新），与上述语义一致。
- [ ] 2.3 文档：在 `docs/guides/RECORDER_PYTHON_OUTPUT.md` 或采集规范中说明「图形验证码步骤为必选暂停，不做条件检测」。

## 3. 删除规则放宽（P1）

- [ ] 3.1 后端：在 `DELETE /component-versions/{version_id}` 中，将可删除条件调整为「非 A/B 测试中」且「已禁用」；即 `!is_testing && !is_active` 即可删除，不再要求 `!is_stable`。批量注册的稳定版在禁用后也可删除。
- [ ] 3.2 前端：删除按钮显示条件与后端一致，`!row.is_testing && !row.is_active`，使已禁用版本显示删除按钮。
- [ ] 3.3 可选：删除稳定版时，若存在同组件其他版本，提示是否将另一版本提升为稳定版；或仅允许删除已禁用的稳定版。

## 4. 组件版本管理体验（P2，可选）

- [ ] 4.1 测试结果或列表展示「实际执行文件」：在测试进度/结果中返回或展示 `file_path` 或「实际执行的组件类名」，便于用户确认测试的是当前选中版本。
- [ ] 4.2 同平台同类型多稳定版提示：在列表或筛选逻辑中，当同一 platform 下同一 component_type 存在多个 is_stable=True 的版本时，在 UI 上标出冲突或提示，引导用户只保留一个稳定版。
- [ ] 4.3 组件类型标签：在列表中用标签或颜色区分 login / navigation / export 等类型，减少混淆。

## 5. 验收与文档

- [ ] 5.1 验收：在组件版本管理页选择 `miaoshou_login` 版本进行测试，确认执行的是 `miaoshou_login.py` 且验证码步骤会暂停并展示截图；禁用某版本后确认可删除；验证码输入回传后流程继续并正确判断登录成功与否。
- [ ] 5.2 更新 CHANGELOG 或相关文档，记录「组件版本测试执行一致性」「删除规则」「验证码必选暂停」的变更说明。
