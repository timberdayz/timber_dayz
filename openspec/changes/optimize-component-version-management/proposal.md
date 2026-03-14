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
7. **file_path 已命中但类解析失败**：测试链路在 `tools/test_component.py` 中按 `component_name` 推断类名（如 `login -> MiaoshouLogin`），而历史版本文件可能是 `MiaoshouMiaoshouLogin` 等旧命名，导致 `Failed to load Python component: login`。该问题会阻断「选择版本后开始测试」主流程，属于 P0。

## What Changes

### 0. 组件唯一性与更新工作流（P0）

- **方案 A**：组件唯一性按 (platform, component_type) 约束，同一平台同一类型只允许一个逻辑组件；component_name 标准化为 `{platform}/{component_type}`（login/navigation）或 `{platform}/{domain}_export`（导出类）。**子域导出**：有子类型的数据域（如 services 的 agent、ai_assistant）按子类型分别录制与保存，各自对应独立 component_name（如 `services_agent_export`、`services_ai_assistant_export`），不是一个大 services 组件在一次流程中串联导出人工+AI；执行器按子域分别调用对应组件。**旧组件删除**：迁移时删除所有不符合标准化 component_name 的 ComponentVersion 记录及对应旧 .py 文件，避免后续误用；采集模块完全重构后将**重新录制**。
- **方案 C**：录制保存时「更新该组件」而非新建组件；保存行为 = 为该组件创建**新版本**，不创建新的 component_name。
- **版本工作流**：新版本默认非稳定；用户测试通过后「提升为稳定版」；生产仅使用稳定版。
- **版本号 patch 递增**：在应用层解析语义版本（major.minor.patch），取当前最大版本后 +1，不得依赖 SQL `MAX(version)` 字典序（否则 `1.0.9` > `1.0.10`）。
- **文件策略**：每个版本对应**独立版本化 file_path**（如 `login_v1_1_0.py`，点号转下划线），DB 中仅保存相对于 PROJECT_ROOT 的相对路径；不再引入主文件 + 草稿文件双轨模式，避免与版本表语义冲突。版本回滚与并行测试一律通过版本化文件名与 ComponentVersion 记录管理。

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

- 当前 executor_v2 选出版本后仍按 comp_name 调用 `build_component_dict_from_python`，未使用 `selected_version.file_path`，导致生产执行到错误文件。需改造为：（1）`_load_component_with_version` 在 selected_version 非空且 file_path 以 .py 结尾时，调用 `load_python_component_from_path(selected_version.file_path)` 构建 component dict，不得再调用 `build_component_dict_from_python`；（2）`_execute_python_component` 当 component dict 含 `_python_component_class`（由 file_path 加载）时，直接使用该类实例化执行 `run(page)`，不得再调用 adapter 按 comp_name 重新加载；（3）从 file_path 通过 `importlib.util.spec_from_file_location` 加载时，模块名须唯一（如 file_path 哈希或 version_id），避免 sys.modules 缓存导致多版本加载错误。**主组件与子组件范围（统一口径）**：本变更主组件为 execution_order 中独立槽位组件（login、navigation、export、date_picker、shop_switch、filters），均按 `selected_version.file_path` 加载；仅 export 内部 `component_call` 调用链中的子调用仍可暂按 adapter 默认加载（comp_name），后续迭代再扩展子调用链的版本化。

### 6. 前端页面结构重构（P2）

- **单 Tab 结构**：版本管理页仅保留「全部版本」一个 Tab，以列表为中心展示所有组件版本信息，列包含「组件名称」「实际执行文件」「状态」「成功率」「使用统计」「操作」等。
- **概览与按平台信息下沉**：原「概览」「按平台」中的统计与冲突告警信息（如版本总数、稳定版数、多稳定版冲突提示）下沉为列表上方的统计卡片与提醒区域，避免多层 Tab 增加操作复杂度。

### 7. 组件测试环境与生产对齐（P0）

- **非登录组件测试前登录/复用会话**：测试 export、navigation、date_picker、filters 等非登录组件时：
  - 若未显式 `skip_login`，首先尝试通过 `SessionManager` 按 (platform, account_id) 加载已存在的 `storage_state`，若有效则用其创建 context，在该 context 中直接执行当前组件；
  - 若无有效会话，则自动选择该平台 login 的当前稳定版（`is_stable=True`），按 `version.file_path` 加载登录组件，并在同一 browser/context 中通过 `_run_login_with_verification_support` 完成登录（支持验证码暂停与回传），登录成功后继续执行当前非登录组件；
  - 登录/会话不可用或登录失败时，测试直接失败并在结果中标记为「login/session 阶段错误」，避免将登录问题误判为导出/导航组件问题。
- **一账号一指纹与持久会话**：组件测试应与生产采集一致，使用「按 account_id 的 `SessionManager.load_session` 得到 `storage_state` + `DeviceFingerprintManager` 指纹」创建 context（`browser.new_context(storage_state=..., **fp_options)`，与 `CollectionExecutorV2.execute` 相同，不使用 `launch_persistent_context`）；account_id 缺失时测试失败并明确报错，强制用户选择账号。
- **阶段可观测性**：单组件测试的进度与结果结构中需区分「login 阶段」与「业务阶段」（如 `phase: "login"`、`phase: "export"`、`phase: "navigation"`），并包含具体组件版本信息（如 `miaoshou/login v1.0.0`、`miaoshou/orders_export v1.0.0`）；前端测试弹窗在失败时展示失败阶段与组件，便于快速定位问题，而不仅是一句通用错误文案。
- **发现模式组件（date_picker / filters）测试策略**：
  - 组件按两类管理：**可独立测试组件**（login/navigation/export 等，或显式声明完整测试场景的 date_picker/filters）与 **仅在完整采集链路中验证的组件**（多数通过发现模式得到的控件）。
  - 为组件增加可选元数据（如 `test_mode`、`test_config`）：  
    - `test_mode="flow_only"`：仅通过 `CollectionExecutorV2.execute` 的完整「登录→导航→日期/筛选→导出」任务进行验证，版本管理页不暴露单独「测试组件」按钮；  
    - `test_mode="standalone"` + 有效 `test_config` 时，允许在版本管理页进行单组件测试，其中 `test_config` 至少包含：
      - `url`：测试时应导航到的页面 URL；
      - `pre_steps`：在执行组件前需要完成的页面准备步骤（如打开筛选面板、切换 Tab）；
      - `assertions`：执行后需要满足的断言（如表格存在、结果条数或日期范围合理）。
  - 单组件测试工具在检测到 `standalone + test_config` 时，先按 `url + pre_steps` 构造上下文，再执行 date_picker/filters 组件；未声明或 `flow_only` 的组件则仅在完整采集任务中通过集成级测试进行验证。

### 8. file_path 加载的类入口稳定性（P0）

- 测试链路在按 `version.file_path` 导入模块后，**不得只依赖 component_name 推断类名**；应优先按类元数据匹配（`platform`、`component_type`），再回退命名约定，兼容历史生成类名（如 `MiaoshouMiaoshouLogin`）。
- 若仍无法定位组件类，错误信息必须包含 `version_id`、`file_path`、模块内候选类列表与匹配规则说明，便于验收与运维定位。
- 生成器与保存链路应保持「可稳定发现入口类」的一致约定（可选：显式入口类名/模块导出），避免未来再次依赖脆弱命名猜测。

### 9. 前端测试链路契约收敛（P1）

- **验证码截图 URL 契约**：前端 `getTestVerificationScreenshotUrl` 必须基于统一 API Base URL 生成可访问路径，禁止依赖不稳定对象属性（如业务 API 对象上的 `defaults`）拼接，确保 `verification_required` 时截图可稳定展示。
- **测试状态轮询生命周期**：前端轮询必须具备可控终止策略：测试完成/失败自动停止、关闭测试弹窗停止、异常达到重试上限或超时停止并提示，避免后台无限轮询。
- **筛选与类型映射一致性**：组件类型筛选项与标准化 component_name 解析规则保持一致，覆盖版本管理中可独立管理的类型（至少 login/navigation/export/date_picker/shop_switch/filters），避免筛选结果与后端语义偏差。

### 10. 测试结果可观测性增强（P1）

- 测试结果与状态查询接口需返回失败阶段信息（如 `phase=login|navigation|export|date_picker|filters|session`）及对应组件版本标识（如 `phase_component_name`、`phase_component_version`），前端在失败提示与结果区域显式展示。
- 当发生组件加载失败、会话失败、登录失败等前置阶段错误时，前端不得仅显示通用失败文案，应展示阶段、组件、关键错误详情，降低排障成本。

### 11. file_path 安全边界（P0）

- `ComponentVersion.file_path` 虽存相对路径，但加载前必须做安全校验：归一化后的绝对路径必须位于允许目录（如 `modules/platforms/**/components/`）内，禁止路径穿越（`..`、跨目录逃逸）与任意文件加载。
- 当 file_path 不满足安全边界时，加载应失败并返回明确错误（包含 version_id、file_path 与安全校验失败原因），不得回退为宽松加载。

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
  - `tools/test_component.py`（按 file_path 导入后的类发现策略：元数据优先、命名兜底、错误可观测性）
  - `tools/test_component.py`（测试时注入 component_class；验证码回传使用同一注入类；非登录组件前自动登录/复用会话；测试环境与生产对齐：一账号一指纹与持久会话）
  - `backend/services/steps_to_python.py`（验证码步骤 unconditional）
  - `frontend/src/views/ComponentVersions.vue`（删除按钮条件、实际执行文件展示、冲突提示、Tab 结构）
  - `frontend/src/views/ComponentRecorder.vue`（保存时由平台+类型推导目标组件；export 时 payload 必须传 data_domain；`POST /recorder/generate-python` 与 save 的 component_name 推导规则一致）
- **已知局限**：生产执行器按 file_path 加载需本变更完成；完成后版本管理的「稳定版」与生产执行将一致。
- **采集环境部署**：所有采集执行环境（backend、collection 容器、本地）需正确配置 `PROJECT_ROOT`；持久会话与指纹需 `DATA_DIR`（或等效）。**file_path 存储规范**：DB 中 ComponentVersion.file_path 统一存**相对路径**（相对于 PROJECT_ROOT），部署时 PROJECT_ROOT 在不同环境可不同（Docker 内 `/app`，本地为仓库根），保证跨环境一致。
