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

- **方案 A**：组件唯一性按 (platform, component_type) 约束，同一平台同一类型只允许一个逻辑组件；component_name 标准化为 `{platform}/{component_type}`（login/navigation）或 `{platform}/{domain}_export`（导出类）。**子域导出**：有子类型的数据域（如 services 的 agent、ai_assistant）按子类型分别录制与保存，各自对应独立 component_name（如 `services_agent_export`、`services_ai_assistant_export`），不是一个大 services 组件在一次流程中串联导出人工+AI；执行器按子域分别调用对应组件。**旧组件删除**：迁移时删除所有不符合标准化 component_name 的 ComponentVersion 记录及对应旧 .py 文件，避免后续误用；采集模块完全重构后将**重新录制**。
- **方案 C**：录制保存时「更新该组件」而非新建组件；保存行为 = 为该组件创建**新版本**，不创建新的 component_name。
- **版本工作流**：新版本默认非稳定；用户测试通过后「提升为稳定版」；生产仅使用稳定版。
- **版本号 patch 递增**：在应用层解析语义版本（major.minor.patch），取当前最大版本后 +1，不得依赖 SQL `MAX(version)` 字典序（否则 `1.0.9` > `1.0.10`）。
- **文件策略**：每个版本对应独立 file_path（如 `login_v1.1.0.py`），或采用主文件 + 草稿文件（`login.py` + `login_draft.py`）；提升稳定时草稿覆盖主文件。优先采用版本化文件名，便于回滚与并行测试。

### 1. 测试执行与选中版本一致（P0）

- 测试路径必须使用从 `version.file_path` 加载到的组件类执行，不得再按 component_type 调用 `adapter.login()` 等内部按模块名加载的接口。
- **验证码回传**：`adapter.login()` 内部在有 `override_login_class` 时必须使用注入类；否则改造 `_run_login_with_verification_support` 接收 `run_fn` 参数，首次与二次均调用同一 `run_fn`，确保回传后仍执行选中版本。
- 所有 component_type（login、navigation、export、date_picker、shop_switch、filters）均须支持注入；若版本管理可测试 shop_switch、filters，适配器亦需对应 override 参数。

### 2. 验证码步骤 unconditional 暂停（P0）

- 对图形验证码步骤，生成「到达即等待 1s → 截图 → raise VerificationRequiredError」，移除 `count()>0` / `is_visible()` 及 `except Exception: pass`。

### 3. 删除规则放宽（P1）

- 可删除条件：`!is_testing && !is_active`。批量注册的稳定版在禁用后也可删除。

### 4. 组件版本管理体验增强（P1）

- 列表与测试弹窗显式展示「实际执行文件」（file_path）。
- 同平台同类型多稳定版时给出冲突提示。
- 组件类型标签可视化。

### 5. 生产执行器按 file_path 加载（P0）

- 当前 executor_v2 选出版本后仍按 comp_name 调用 `build_component_dict_from_python`，未使用 `selected_version.file_path`，导致生产执行到错误文件。需改造为：（1）`_load_component_with_version` 在 selected_version 非空且 file_path 以 .py 结尾时，调用 `load_python_component_from_path(selected_version.file_path)` 构建 component dict，不得再调用 `build_component_dict_from_python`；（2）`_execute_python_component` 当 component dict 含 `_python_component_class`（由 file_path 加载）时，直接使用该类实例化执行 `run(page)`，不得再调用 adapter 按 comp_name 重新加载；（3）从 file_path 通过 `importlib.util.spec_from_file_location` 加载时，模块名须唯一（如 file_path 哈希或 version_id），避免 sys.modules 缓存导致多版本加载错误。**主组件与子组件范围**：本变更主组件（login、navigation、export）按 `selected_version.file_path` 加载；export 内 `component_call` 调用的 date_picker、filters、shop_switch 暂按 adapter 默认加载（comp_name），不纳入本变更版本管理；后续迭代可扩展子组件版本化。

### 6. 前端页面结构重构（P2）

- **Tab 1 概览**：统计卡片、最近活动、冲突告警、快速入口。
- **Tab 2 按平台**：树形/分组浏览，按 platform → component_type → 组件，一眼看出当前生产用哪一版。
- **Tab 3 全部版本**：表格视图，列包含「实际执行文件」，状态、成功率、操作。

### 7. 组件测试环境与生产对齐（P0）

- **非登录组件测试前登录**：测试 export、navigation、date_picker、filters 等非登录组件时，必须先完成自动登录或复用该账号持久会话；若未提供 skip_login 且登录/会话不可用，则不得执行该组件测试，直接报错。**登录版本选择**：自动登录应使用该平台 login 的当前稳定版（is_stable=True），按 file_path 加载，与生产一致。
- **一账号一指纹与持久会话**：组件测试应与生产采集一致，使用「按 account_id 的 SessionManager.load_session 得到 storage_state + DeviceFingerprintManager 指纹」建 context（`new_context(storage_state=..., **fp_options)`，与 executor_v2 相同，不使用 launch_persistent_context）；account_id 缺失时测试失败并明确报错，强制用户选择账号。

**API 影响**：`POST /recorder/save` 与 `POST /recorder/generate-python` 的 component_name 由 platform+component_type 推导（export 需 data_domain，子域 export 如 services:agent 需 sub_domain）；**校验**：export 时 data_domain 缺失返回 400；当 data_domain 有子类型且前端选择子域导出时，sub_domain 必填，否则 400。**sub_domain 子类型判定**：后端维护「有子类型的数据域」配置（如 `services` → `["agent","ai_assistant"]`），可硬编码或配置化；仅当 data_domain 在此列表中且前端传 sub_domain 时才校验 sub_domain 必填。保存行为从「同 file_path 则 UPSERT」改为「创建新版本 + 版本化 file_path」。**GeneratePythonRequest**：请求体与 RecorderSaveRequest 对齐，增加 data_domain（export 必填）、sub_domain（子域 export 必填）；component_name 由 platform+component_type+data_domain+sub_domain 推导，不再必填或废弃。**兼容策略**：为兼容旧客户端，可保留 component_name 字段但由后端忽略；过渡期后可选废弃。路径与请求结构可保持兼容，但语义变更，调用方需知悉。

## Impact

- **迁移策略**：删除旧 ComponentVersion 记录及不符合标准化 component_name 的旧 .py 文件；**保留**标准化命名的主文件（如 `login.py`、`navigation.py`、`orders_export.py` 等）作为 fallback，供无版本记录时 `build_component_dict_from_python` 加载；仅删除非标准化文件（如 `miaoshou_login.py`）。采集模块完全重构完毕后将重新录制并写入新版本。
- **受影响规范**：`data-collection`（组件测试执行、验证码步骤语义）、`component-version-management`（删除规则、测试一致性、UI 结构）。
- **受影响代码**：
  - `modules/core/db/schema.py`（可选：ComponentVersion 约束或校验逻辑）
  - `backend/services/component_version_service.py`（component_name 标准化、唯一性校验）
  - `backend/routers/component_recorder.py`（保存时更新已有组件、创建新版本，不新建 component_name）
  - `backend/routers/component_versions.py`（删除条件、可选冲突检测、component_name 标准化）
  - `modules/apps/collection_center/python_component_adapter.py`（适配器支持注入指定组件类）
  - `modules/apps/collection_center/executor_v2.py`（按 component_type 构造 component_name；按 selected_version.file_path 加载组件）
  - `modules/apps/collection_center/component_loader.py`（新增从 file_path 加载的方法，供执行器与测试使用）
  - `tools/test_component.py`（测试时注入 component_class；验证码回传使用同一注入类；非登录组件前自动登录/复用会话；测试环境与生产对齐：一账号一指纹与持久会话）
  - `backend/services/steps_to_python.py`（验证码步骤 unconditional）
  - `frontend/src/views/ComponentVersions.vue`（删除按钮条件、实际执行文件展示、冲突提示、Tab 结构）
  - `frontend/src/views/ComponentRecorder.vue`（保存时由平台+类型推导目标组件；export 时 payload 必须传 data_domain；`POST /recorder/generate-python` 与 save 的 component_name 推导规则一致）
- **已知局限**：生产执行器按 file_path 加载需本变更完成；完成后版本管理的「稳定版」与生产执行将一致。
- **采集环境部署**：所有采集执行环境（backend、collection 容器、本地）需正确配置 `PROJECT_ROOT`；持久会话与指纹需 `DATA_DIR`（或等效）。**file_path 存储规范**：DB 中 ComponentVersion.file_path 统一存**相对路径**（相对于 PROJECT_ROOT），部署时 PROJECT_ROOT 在不同环境可不同（Docker 内 `/app`，本地为仓库根），保证跨环境一致。
