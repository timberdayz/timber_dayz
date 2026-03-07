# Tasks: 采集组件版本管理模块重构

**目标**：组件唯一性（方案 A+C）、修复「测试 A 执行 B」、放宽删除规则、验证码必选暂停，并增强体验（实际执行文件、冲突提示、可选 Tab 结构）。

## 0. 组件唯一性与录制保存（P0）

- [ ] 0.1 component_name 标准化：定义 `{platform}/{component_type}` 与 `{platform}/{domain}_export` 规则；executor_v2 与 ComponentVersionService 统一按此构造 component_name。
- [ ] 0.2 录制保存逻辑：`POST /recorder/save` 时，由 platform + component_type 推导 component_name，为该组件创建**新版本**（递增 version），写入版本化 file_path（如 `{name}_v{version}.py`），新版本默认非稳定；不创建新的 component_name。
- [ ] 0.3 批量注册：批量注册时 component_name 按标准化规则构造，禁止生成 miaoshou/miaoshou_login 等与 component_type 不一致的名称；已存在的重复 component_name 可保留但加告警。
- [ ] 0.4 迁移脚本（可选）：合并存量 miaoshou/miaoshou_login 与 miaoshou/login 等重复记录，或提供迁移指南供用户手动处理。

## 1. 测试执行使用选中组件（P0）

- [ ] 1.1 适配器支持「指定组件类」：在 `PythonComponentAdapter` 或 `create_adapter` 中增加可选参数（如 `override_login_class`、`override_navigation_class`、`override_export_class`、`override_date_picker_class`），当提供时，`login()` / `navigate()` / `export()` / `date_picker()` 使用注入类实例执行，而非 `_load_component_class(...)` 按模块名加载。
- [ ] 1.2 测试工具传入组件类：在 `tools/test_component.py` 的 `_test_python_component_with_browser` 中，将已加载的 `component_class` 按 component_type 注入适配器，确保执行 `version.file_path` 对应实现。
- [ ] 1.3 **验证码恢复路径**：`_run_login_with_verification_support` 在用户回传验证码后二次调用 `adapter.login(page)` 时，必须使用同一注入的 component_class。
- [ ] 1.4 回归：对同一 component_name 的多个版本（如 miaoshou/login v1.0.0 与 v1.1.0），分别测试（含验证码回传），验证首次与回传后二次执行均使用对应 version.file_path。

## 2. 验证码步骤 unconditional 暂停（P0）

- [ ] 2.1 生成器修改：在 `backend/services/steps_to_python.py` 中，对图形验证码步骤（step_group 或 scene_tags 含 captcha/captcha_graphical/graphical_captcha），生成「固定短等待 1s → 截图 → raise VerificationRequiredError」，移除 `if await _cap_inp.count() > 0`、`is_visible()` 判断及 `except Exception: pass`。
- [ ] 2.2 已存在组件：对 `modules/platforms/miaoshou/components/miaoshou_login.py` 中验证码块改为 unconditional。
- [ ] 2.3 文档：在 `docs/guides/RECORDER_PYTHON_OUTPUT.md` 说明「图形验证码步骤为必选暂停，不做条件检测」。

## 3. 删除规则放宽（P1）

- [ ] 3.1 后端：`DELETE /component-versions/{version_id}` 可删除条件调整为 `!is_testing && !is_active`，不再要求 `!is_stable`。
- [ ] 3.2 前端：删除按钮显示条件 `!row.is_testing && !row.is_active`。
- [ ] 3.3 可选：删除稳定版时若存在同组件其他版本，提示是否将另一版本提升为稳定版。

## 4. 组件版本管理体验（P1）

- [ ] 4.1 实际执行文件展示：在版本列表增加「实际执行文件」列（file_path）；测试弹窗顶部显式展示 file_path。
- [ ] 4.2 同平台同类型多稳定版冲突提示：当同一 platform 下同一 component_type 存在多个 is_stable=True 时，在 UI 标出冲突或警告。
- [ ] 4.3 组件类型标签：在列表中用标签/颜色区分 login / navigation / export 等类型。

## 5. 前端页面结构（P2，可选）

- [ ] 5.1 Tab 概览：统计卡片、最近活动、冲突告警、快速入口（去录制、批量注册）。
- [ ] 5.2 Tab 按平台：树形/分组浏览 platform → component_type → 组件，展示当前生产版本。
- [ ] 5.3 Tab 全部版本：保留现有表格为「全部版本」Tab，确保列含「实际执行文件」。

## 6. 验收与文档

- [ ] 6.1 验收：选择某组件版本测试，确认执行的是该 version.file_path 对应文件且验证码会暂停；禁用后确认可删除；验证码回传后流程正确继续；录制保存创建新版本而非新 component_name。
- [ ] 6.2 更新 CHANGELOG 或相关文档，记录「组件版本测试执行一致性」「删除规则」「验证码必选暂停」「实际执行文件展示」等变更。
