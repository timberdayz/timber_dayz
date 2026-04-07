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

### 12. 采集脚本现实 Web 稳健性补强（P0）

- **定位器唯一性契约**：对将被 `click/fill/expect(...).to_be_visible` 使用的目标 locator，必须满足当前作用域唯一命中；出现多匹配时先收敛到稳定容器（form/dialog/frame/row）再定位，禁止默认用 `.first/.nth()` 掩盖歧义。
- **反模式禁用**：禁止 `count()+is_visible()` 单次判断后操作、`except Exception: pass` 吞错继续、以固定 sleep 代替条件等待。
- **失败可观测性**：关键失败结果需包含 `phase + component + version + url + selector_context`，验证码与关键失败路径必须可留存截图。
- **导航完成双信号**：页面就绪采用“URL/路由特征 + 关键元素可见”联合判断，不以单一 `networkidle` 作为稳定性依据。
- **文档治理**：`COLLECTION_SCRIPT_WRITING_GUIDE` 作为采集脚本规范基线；录制/模板文档与其冲突时需在本变更中同步收敛，避免新组件继续复制过时模式（如 sync API、YAML 流程、UPSERT 旧语义）。

### 13. 组件录制生成器合规修复（P0）

- **现状问题（本次审查）**：生成器当前仍包含与新规范冲突的输出模式，如可选步骤统一 `except Exception: pass`、`wait` 步骤直出 `wait_for_timeout`、多个分支默认 `.first` 与 `count()+is_visible()` 判定，且缺少“先容器后元素”的作用域收敛策略。
- **修复目标**：
  1. 生成代码默认不产生 `except Exception: pass`（改为可观测可诊断的受控错误处理）；
  2. `wait` 步骤优先生成条件等待（目标元素/状态），固定 sleep 仅在显式理由下生成；
  3. locator 生成遵循“先容器后元素 + 唯一性约束”，减少 page 根作用域宽匹配；
  4. 验证码恢复与关键点击路径不再默认 `.first`，改为可诊断的唯一性策略；
  5. lint 从“提示级”升级为“质量门禁”：关键反模式升级为 `error` 且默认阻断保存（保留可配置开关）。
- **前端提示增强**：录制页 lint 提示需区分严重级别（error/warning），并给出可操作修复建议，避免“看到告警但不知道怎么改”。
- **补充修复（本轮复核新增）**：
  6. 可选步骤异常处理代码必须可执行，禁止在生成代码里引用生成器侧变量（如 `i/action`）导致运行期 NameError；
  7. lint 门禁与 wait 策略需一致：仅“无理由固定等待”阻断保存；有显式固定等待理由时允许保存（可降为 warning）；
  8. `.first/.nth` 应实现“有注释依据可放行、无注释阻断”的受控策略，避免与规范口径冲突；
  9. 作用域收敛需覆盖 iframe/row/dialog 等，不应仅覆盖 login form；
  10. lint 阻断必须作用于“最终落盘代码”（含 success_criteria 注入后），避免“先 lint 再注入”导致门禁绕过；
  11. login 组件作用域收敛不得写死 `get_by_role("form")` 单一路径，应支持“语义容器优先 + 业务容器兜底”的多候选容器策略，避免真实页面 `form=0` 直接失败；
  12. URL 导航契约需显式化：login 组件测试与执行应具备“URL 来源优先级 + 导航前状态判定 + 导航后双信号确认（URL/路由特征 + 关键元素可见）”，禁止依赖“碰巧已在目标页”。

### 14. fallback 一致性保护（P0）

- **问题**：当 `selected_version is None` 走 comp_name 回退时，存在“预期版本信息缺失、实际执行文件退化”的一致性风险。
- **要求**：
  1. fallback 执行必须输出强告警（结构化字段至少含 platform/component_type/component_name/reason）；
  2. 提供可配置 `fail_fast_on_missing_selected_version`，在关键环境可直接失败而非静默回退；
  3. 前端与日志可见该次执行是否发生 fallback，避免“以为按版本执行，实际走回退”。

### 15. 提案关闭门槛（P0）

- 以下条件未满足时，变更不得归档：`1.5`（多版本回归）、`6.1`（综合人工验收）、`7.4`（现实 Web 四类补充用例）。
- 以下能力必须落地后方可视为“质量闭环”：`7.3.2`（关键反模式阻断保存）与 `8.7`（generate-python 参数对齐）。
- 口径一致性要求：`8.2`（wait 策略）、`8.4`（.first/.nth 约束）、`8.8`（回归覆盖）必须与 lint 实际门禁规则一致；若存在“提案允许但门禁阻断”的冲突，不得归档。
- 本轮新增口径一致性要求：login 容器收敛策略与 URL 导航契约（对应 tasks `8.14`、`8.15`）未落地前，不得宣告“现实 Web 稳健性闭环完成”。

### 16. 生成器输出与 URL 导航优化范围（P0）

- **当前生成器输出类型（现状）**：
  1. `login`：生成 `LoginComponent`，含验证码暂停与回传恢复路径；
  2. `export`：生成 `ExportComponent`，支持导出模式骨架；
  3. `navigation/date_picker/filters/others`：生成通用 `ResultBase` 组件骨架。
- **当前已覆盖场景（现状）**：
  1. 反模式门禁（吞错、无理由固定等待、无依据 `.first/.nth`、`count()+is_visible()`）；
  2. 链式作用域收敛（iframe/dialog/row）；
  3. 验证码暂停与回传后的同页恢复路径。
- **当前已识别缺口（本轮新增）**：
  1. login 容器收敛默认写死 `get_by_role("form")`，在无语义 form 的真实页面会 `count=0` 直接失败；
  2. login URL 导航依赖录制步骤“是否碰巧包含 navigate”，缺少统一导航契约。
- **URL 导航目标设计（本变更必须落地）**：
  1. URL 来源优先级：`login_url_override > account.login_url > 平台默认登录 URL`；
  2. 导航前状态判定：若已处于目标登录页且关键元素可见，可跳过 goto；
  3. 导航后成功判定：必须满足“URL/路由特征 + 关键元素可见”双信号；
  4. 失败可观测性：返回 `current_url`、`target_url`、`phase`、`component`、`version`、`selector_context`；
  5. 禁止仅用 `networkidle`/`domcontentloaded` 单信号判定登录页就绪。
- **最小上线顺序（执行编排）**：
  - **S1（止血）**：先落地 `8.14`，修复 login 容器写死 `role=form` 的首步失败问题，确保人工验收可继续；
  - **S2（契约）**：再落地 `8.15.1~8.15.4`，完成 URL 来源优先级、导航前后判定与可观测性；
  - **S3（质量）**：最后落地 `8.15.5` 回归与真实页面验收，补齐归档门槛证据。

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
- **受影响文档**：
  - `docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md`（新增现实 Web 强约束：唯一性契约、反模式禁用、可观测性契约）
  - `docs/guides/RECORDER_PYTHON_OUTPUT.md`（与版本化保存语义、验证码语义保持一致）
  - `docs/guides/PYTHON_COMPONENT_TEMPLATE.md`、`docs/guides/COMPONENT_RECORDING_GUIDE.md`、`docs/guides/recording_rules.md`（历史示例收敛，避免反向引导）
- **已知局限**：生产执行器按 file_path 加载需本变更完成；完成后版本管理的「稳定版」与生产执行将一致。
- **采集环境部署**：所有采集执行环境（backend、collection 容器、本地）需正确配置 `PROJECT_ROOT`；持久会话与指纹需 `DATA_DIR`（或等效）。**file_path 存储规范**：DB 中 ComponentVersion.file_path 统一存**相对路径**（相对于 PROJECT_ROOT），部署时 PROJECT_ROOT 在不同环境可不同（Docker 内 `/app`，本地为仓库根），保证跨环境一致。
- **关联提案**：验收过程中发现的生成器架构问题（门卫检测和容器发现注入导致真实页面首步失败）已拆分到独立提案 `refactor-generator-runtime-separation` 跟踪。该提案移除了生成器中的框架逻辑，将页面就绪检测移至运行时/测试框架层。
