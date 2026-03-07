# Change: 采集组件版本管理模块重构

## Why

录制相关能力已优化完毕，组件版本管理模块需基于需求重新设计，避免沿用旧设计带来的问题。业界主流实践（Polyaxon Component Hub、Mendix Marketplace、n8n Node Versioning、ScriptRunner Registry 等）均强调：**版本与执行明确绑定**、**实际执行文件可见**、**删除/启用规则清晰**。

### 当前问题

1. **测试 A 组件却执行 B 组件**：用户对 `miaoshou_login` v1.0.0 点击「测试」时，后端按 `version.file_path` 加载了 `miaoshou_login.py` 的组件类，但测试分支调用 `adapter.login(page)`，适配器内部固定 `_load_component_class("login")`，实际执行的是 `login.py`，导致测试不可信。
2. **禁用的组件无法删除**：删除条件为 `!is_stable && !row.is_testing`，批量注册默认 `is_stable=True`，禁用后仍无法删除。
3. **验证码步骤静默穿透**：图形验证码步骤使用 `count()>0` / `is_visible()` 检测，被 `except Exception: pass` 吞掉后继续点登录，与「到达即暂停」业务预期不符。
4. **同平台多组件易混淆**：缺少「实际执行文件」的可视化与冲突提示，易造成「测 A 执行 B」误判。
5. **以版本列表为主，缺少按能力组织**：无法快速看出「某平台某类型当前生产用哪个组件」。
6. **组件唯一性缺失**：同一 (platform, component_type) 可存在多个 component_name（如 miaoshou/login 与 miaoshou/miaoshou_login），易导致生产执行到错误组件。

## What Changes

### 0. 组件唯一性与更新工作流（P0）

- **方案 A**：组件唯一性按 (platform, component_type) 约束，同一平台同一类型只允许一个逻辑组件；component_name 标准化为 `{platform}/{component_type}`（login/navigation）或 `{platform}/{domain}_export`（导出类）。
- **方案 C**：录制保存时「更新该组件」而非新建组件；保存行为 = 为该组件创建**新版本**，不创建新的 component_name。
- **版本工作流**：新版本默认非稳定；用户测试通过后「提升为稳定版」；生产仅使用稳定版。
- **文件策略**：每个版本对应独立 file_path（如 `login_v1.1.0.py`），或采用主文件 + 草稿文件（`login.py` + `login_draft.py`）；提升稳定时草稿覆盖主文件。优先采用版本化文件名，便于回滚与并行测试。

### 1. 测试执行与选中版本一致（P0）

- 测试路径必须使用从 `version.file_path` 加载到的组件类执行，不得再按 component_type 调用 `adapter.login()` 等内部按模块名加载的接口。
- 验证码回传后二次执行也须使用同一注入的组件类。
- 所有 component_type（login、navigation、export、date_picker）均须支持注入。

### 2. 验证码步骤 unconditional 暂停（P0）

- 对图形验证码步骤，生成「到达即等待 1s → 截图 → raise VerificationRequiredError」，移除 `count()>0` / `is_visible()` 及 `except Exception: pass`。

### 3. 删除规则放宽（P1）

- 可删除条件：`!is_testing && !is_active`。批量注册的稳定版在禁用后也可删除。

### 4. 组件版本管理体验增强（P1）

- 列表与测试弹窗显式展示「实际执行文件」（file_path）。
- 同平台同类型多稳定版时给出冲突提示。
- 组件类型标签可视化。

### 5. 前端页面结构重构（P2）

- **Tab 1 概览**：统计卡片、最近活动、冲突告警、快速入口。
- **Tab 2 按平台**：树形/分组浏览，按 platform → component_type → 组件，一眼看出当前生产用哪一版。
- **Tab 3 全部版本**：表格视图，列包含「实际执行文件」，状态、成功率、操作。

**无破坏性变更**：API 路径与请求/响应结构保持不变；仅后端执行逻辑、删除校验条件、生成器输出及前端展示结构变更。

## Impact

- **受影响规范**：`data-collection`（组件测试执行、验证码步骤语义）、`component-version-management`（删除规则、测试一致性、UI 结构）。
- **受影响代码**：
  - `modules/core/db/schema.py`（可选：ComponentVersion 约束或校验逻辑）
  - `backend/services/component_version_service.py`（component_name 标准化、唯一性校验）
  - `backend/routers/component_recorder.py`（保存时更新已有组件、创建新版本，不新建 component_name）
  - `backend/routers/component_versions.py`（删除条件、可选冲突检测、component_name 标准化）
  - `modules/apps/collection_center/python_component_adapter.py`（适配器支持注入指定组件类）
  - `modules/apps/collection_center/executor_v2.py`（按 component_type 构造 component_name 与版本服务一致）
  - `tools/test_component.py`（测试时注入 component_class；验证码回传使用同一注入类）
  - `backend/services/steps_to_python.py`（验证码步骤 unconditional）
  - `frontend/src/views/ComponentVersions.vue`（删除按钮条件、实际执行文件展示、冲突提示、Tab 结构）
  - `frontend/src/views/ComponentRecorder.vue`（保存时选择「更新现有组件」或由平台+类型推导目标组件）
- **已知局限（本变更不解决）**：生产执行器仍按 ComponentVersionService 选版；若执行器未按 file_path 加载，版本管理的「稳定版」「使用统计」可能与生产实际不一致，需后续变更单独打通。
