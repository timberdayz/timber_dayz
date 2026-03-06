# Change: 组件版本管理优化（测试一致性、删除规则、验证码必选）

## Why

1. **测试 A 组件却执行 B 组件**：用户在组件版本管理页对某版本（如 `miaoshou_login` v1.0.0）点击「测试」时，后端按 `version.file_path` 正确加载了 `miaoshou_login.py` 的组件类，但测试分支中 `component_type == 'login'` 时调用的是 `adapter.login(page)`；适配器内部固定 `_load_component_class("login")`，实际执行的是 `login.py` 中的 `MiaoshouLogin`，导致测试结果与用户选中的版本完全不符，测试不可信。
2. **禁用的组件无法删除**：删除按钮的显示条件为 `!row.is_stable && !row.is_testing`，而批量注册的组件默认 `is_stable=True`，因此即使用户禁用了组件，仍无法删除，无法清理废弃或重复的组件。
3. **验证码步骤应为必选暂停**：当前生成的登录组件在验证码步骤使用「检测 DOM 存在且可见再截图并 raise」的逻辑；若 `is_visible()` 超时或异常会被 `except Exception: pass` 吞掉，脚本继续执行「点击登录」，导致流程跑完才报错。业务上图形验证码环节是必现的，应到达该步骤即截图并暂停，无需条件检测。
4. **同平台多组件易混淆**：存在 `miaoshou login` 与 `miaoshou miaoshou_login` 等相似名称，缺少「实际执行文件」的可视化与冲突提示，容易造成「测 A 执行 B」的误判。

## What Changes

- **测试执行必须使用选中版本对应的组件**：在组件版本测试路径中，当从 `file_path` 加载到具体组件类后，执行时必须使用该类（或通过适配器注入该类），不得再按 `component_type` 调用 `adapter.login()` / `adapter.navigate()` 等内部重新按模块名加载的接口，避免执行到其他文件中的实现。
- **删除规则放宽**：允许在「非 A/B 测试中」且「已禁用」的版本上显示删除并执行删除；或明确「可删除 = 非测试中 && (已禁用 || 非稳定版)」，使批量注册的稳定版在禁用后可被清理。
- **验证码步骤改为无条件暂停**：对录制/生成器中标记为图形验证码的步骤，生成的代码在该步骤**不**做 `count() > 0` / `is_visible()` 等条件判断，到达即截图并抛出 `VerificationRequiredError`，等待用户回传后再继续。
- **组件版本管理体验增强**（可选）：列表或测试结果中展示「实际执行文件」、同平台同类型多稳定版时给出冲突提示、组件类型标签可视化，降低误操作与混淆。

**无破坏性变更**：API 路径与请求/响应结构保持不变；仅后端执行逻辑、删除校验条件与生成器输出内容变更。

## Impact

- **受影响规范**：`data-collection`（组件测试执行、验证码步骤语义）、新增能力 `component-version-management`（版本管理删除规则与测试一致性）。
- **受影响代码**：
  - `modules/apps/collection_center/python_component_adapter.py`（适配器支持注入/使用指定组件类）
  - `tools/test_component.py`（测试时使用从 file_path 加载的组件类；验证码回传后二次执行也须使用注入类）
  - `backend/services/steps_to_python.py`（验证码步骤生成无条件截图与 raise）
  - `backend/routers/component_versions.py`（删除条件与可选冲突检测）
  - `frontend/src/views/ComponentVersions.vue`（删除按钮显示条件、可选展示「实际执行文件」与冲突提示）
- **已知局限（本变更不解决）**：生产采集执行器（executor_v2）仍通过 `adapter.login()` / `adapter.navigate()` 等按模块名加载组件，**不使用** ComponentVersion 的 file_path。版本管理中的「稳定版」「使用统计」「成功率」与实际生产执行可能不一致；用户测试通过的 `miaoshou_login` 与生产实际使用的 `login.py` 可能不同。此问题需后续变更（执行器按 ComponentVersionService 选版并加载 file_path）单独解决。
