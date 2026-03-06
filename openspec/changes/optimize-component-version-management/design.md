# Design: 组件版本管理优化

## Context

- 组件版本管理页通过 `version.file_path` 加载对应 `.py` 文件得到组件类，但测试时对 login 类型调用 `adapter.login(page)`，适配器内部固定加载 `login` 模块，导致执行的是 `login.py` 而非用户选中的 `miaoshou_login.py`。
- 删除逻辑依赖 `!is_stable && !row.is_testing`，批量注册默认 is_stable=True，禁用后仍无法删除。
- 验证码步骤当前为「检测到输入框且可见才截图并 raise」，存在静默穿透，与「验证码必选、到达即暂停」的业务预期不符。

## Goals / Non-Goals

- **Goals**：测试执行与选中版本一致；已禁用版本可删除；验证码步骤到达即暂停。
- **Non-Goals**：不改变采集执行器在生产环境选择组件的逻辑（仍按 ComponentVersionService 选版）；不在此变更中实现验证码自动识别或第三方打码。

## Decisions

### 1. 测试时执行哪个组件类

- **决策**：测试路径必须使用从 `version.file_path` 加载到的组件类执行，而不是由适配器按 `component_type` 再按模块名（如 `login`）加载。**所有 component_type**（login、navigation、export、date_picker）均须改造，避免测试非标准命名组件（如 `miaoshou_custom_navigation`）时仍执行 `navigation.py`。
- **验证码恢复路径**：`_run_login_with_verification_support` 在用户回传验证码后会再次调用 `adapter.login(page)`。该二次调用**必须同样使用注入的 component_class**，否则填入验证码后仍会执行 `login.py` 而非用户选中的 `miaoshou_login.py`。
- **实现选项**：
  - **A. 适配器注入**：`create_adapter(..., override_login_class=component_class)`，`adapter.login(page)` 时若存在 override_login_class 则用该类实例执行；恢复路径二次调用 `adapter.login(page)` 时 adapter 仍使用同一注入类。
  - **B. 测试分支直接执行**：在 `_test_python_component_with_browser` 中，当已从 file_path 加载到 component_class 时，不调用 `adapter.login(page)`，改为传入可调用对象（如 `lambda: component_class(ctx).run(page)`）给 `_run_login_with_verification_support`。该函数需改造：接收 `run_fn` 而非 adapter，首次执行与验证码回传后二次执行均调用 `run_fn()`，不再内部调用 `adapter.login(page)`。
- **选用**：A 更少侵入、复用现有 adapter 的 ctx/guard_overlays；若 adapter 未暴露注入点则采用 B，此时需对 `_run_login_with_verification_support` 做签名级改造（接收执行函数而非 adapter）。

### 2. 删除条件

- **决策**：允许删除「非 A/B 测试中」且「已禁用」的版本；即 `!is_testing && !is_active` 即可删除，不再要求 `!is_stable`。这样批量注册的稳定版在禁用后也可删除。启用中的版本（含非稳定版）不可删除，避免误删正在使用的组件。

### 3. 验证码步骤生成语义

- **决策**：对录制/生成器标记为「图形验证码」的步骤，生成「到达即等待 1s → 截图 → raise VerificationRequiredError」，不生成 `if count() > 0` / `is_visible()` 及 `except Exception: pass`。
- **注意**：若某平台存在「有时无验证码」的登录页，可在后续通过「可选验证码步骤」或条件分支单独支持；本变更统一为必选暂停以符合当前业务。

## Risks / Trade-offs

- **适配器注入**：增加可选参数后，需保证生产路径不传入 override，默认行为不变。
- **删除稳定版**：放宽后用户可能误删唯一稳定版，可通过「删除时校验同组件是否还有稳定版」或仅允许「已禁用的版本可删」降低风险。

## Migration Plan

- 无需数据迁移。部署后现有组件版本与测试行为除上述三点外不变；已存在的 miaoshou_login 等组件需按 2.2 手动改验证码块或重新保存以应用无条件暂停逻辑。

## Open Questions

- **生产执行器与版本管理脱节**：executor_v2 在生产采集时仍通过 `adapter.login()` 等按模块名加载组件，不使用 ComponentVersion.file_path。版本管理中的「稳定版」「使用统计」与实际生产执行可能不一致。本变更仅修复测试路径；生产打通需单独提案。
