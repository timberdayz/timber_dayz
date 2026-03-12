# Tasks: 采集组件版本管理模块重构

**目标**：组件唯一性（方案 A+C）、修复「测试 A 执行 B」、放宽删除规则、验证码必选暂停，并增强体验（实际执行文件、冲突提示、可选 Tab 结构）。

## 0. 组件唯一性与录制保存（P0）

- [x] 0.1 component_name 标准化：定义 `{platform}/{component_type}` 与 `{platform}/{domain}_export`（含 `{platform}/{domain}_{sub}_export`）规则；executor_v2 与 ComponentVersionService 统一按此构造 component_name。**date_picker、shop_switch、filters** 采用 `{platform}/{component_type}`，有独立槽位，可单独录制与版本管理。**子域导出**：有子类型的数据域按子类型分别录制/保存（如 services_agent_export、services_ai_assistant_export），不是一个大组件串联多种子类型。
- [x] 0.2 录制保存逻辑：`POST /recorder/save` 与 `POST /recorder/generate-python` 均使用 platform + component_type（export 需 data_domain，子域 export 如 services:agent 需 sub_domain）推导 component_name；save 时为该组件创建**新版本**（patch 递增，1.0.0→1.0.1），写入版本化 file_path（`{base}_v1_0_1.py`，点号转下划线），**file_path 存相对路径**（相对于 PROJECT_ROOT）；新版本默认非稳定；首次录制 v1.0.0 亦遵循默认 is_stable=False。取代 add-collection-recorder 的 UPSERT 语义。**子类型判定**：后端维护 `DATA_DOMAIN_SUB_TYPES`（如 `{"services": ["agent","ai_assistant"]}`），当 data_domain 在此配置中时 sub_domain 必填。**版本号 patch 递增**：在应用层解析 version 为 (major, minor, patch) 元组，取当前最大版本后 patch+1，不得依赖 SQL `MAX(version)` 字典序（否则 `1.0.9` > `1.0.10`）；保存时在事务内查询该 component_name 所有版本、解析取 max、再递增，或捕获 (component_name, version) 唯一约束冲突后重试。**请求体**：RecorderSaveRequest 必须包含 `platform`、`component_type`；export 时必须包含 `data_domain`；子域 export 必须包含 `sub_domain`。**GeneratePythonRequest**：与 save 对齐。**校验**：export 时 data_domain 缺失则 400；data_domain 有子类型时 sub_domain 缺失则 400。
- [x] 0.3 批量注册：component_name 按标准化规则构造。**新创建版本**默认 is_stable=False，与录制保存一致。版本化文件名解析：`login_v1_1_0.py` → base=login、version=1.1.0、component_name=`{platform}/login`；`orders_export_v1_0_0.py` → base=orders_export、version=1.0.0、component_type=export、data_domain=orders、component_name=`{platform}/orders_export`；`services_agent_export_v1_0_0.py` → base=services_agent_export、domain=services、sub=agent、component_name=`{platform}/services_agent_export`（规则：`*_export` 的 base 去掉 `_export` 得逻辑名，第一段为 data_domain，后续为 sub 或视为整体）。非版本化文件名（如 `login.py`）映射为 component_name=`{platform}/login`、version=1.0.0；重复 component_name 加告警。
- [x] 0.4 component_type 推导：实现从 component_name 解析 platform、component_type 的规则，供列表筛选、冲突检测、按平台分组使用。
- [x] 0.5 迁移脚本：**删除旧组件**：删除 ComponentVersion 表中所有不符合标准化 component_name 的记录（如 miaoshou/miaoshou_login）；**ComponentTestHistory 处理**：删除前先处理关联——删除 `version_id` 指向待删 ComponentVersion 的 ComponentTestHistory 记录（推荐），或将 `version_id` 置 NULL，再删除 ComponentVersion。**文件策略**：删除或归档非标准化旧 .py 文件（如 miaoshou_login.py）；**保留**标准化命名的主文件（如 login.py、navigation.py、orders_export.py）作为 fallback，供无版本记录时 `build_component_dict_from_python(platform, comp_name)` 加载。采集模块完全重构后将**重新录制**并写入新版本。**执行时机**：在 0.2 录制保存逻辑与 component_name 校验上线后执行。**同步更新 execution_order**：若有平台覆盖使用旧 comp_name，改为标准化名称。**component_name 校验**：录制保存、批量注册时校验 component_name 符合规则，禁止录入旧格式。
- [x] 0.6 前端 export 保存传 data_domain/sub_domain：ComponentRecorder 保存 export 组件时，前端 save payload 必须包含 `data_domain`（用户选择或从录制会话带出）；子域 export（如 services:agent）还需传 `sub_domain`；否则后端无法推导 component_name。校验 `ComponentRecorder.vue` 的 saveComponent 中 payload 已添加 `data_domain`（recorderForm.dataDomain）及子域场景的 `sub_domain`。generate-python 改造由 0.2 覆盖，前端调用时传 platform、component_type、data_domain（export）、sub_domain（子域 export）即可。

## 1. 测试执行使用选中组件（P0）

- [x] 1.1 适配器支持「指定组件类」：在 `PythonComponentAdapter` 或 `create_adapter` 中增加可选参数（如 `override_login_class`、`override_navigation_class`、`override_export_class`、`override_date_picker_class`、`override_shop_switch_class`、`override_filters_class`），当提供时对应方法使用注入类实例执行，而非 `_load_component_class(...)` 按模块名加载。
- [x] 1.2 测试工具传入组件类：在 `tools/test_component.py` 的 `_test_python_component_with_browser` 中，将已加载的 `component_class` 按 component_type 注入适配器，确保执行 `version.file_path` 对应实现。
- [x] 1.3 **验证码恢复路径**：确保 `adapter.login()` 在 override 存在时使用注入类；或改造 `_run_login_with_verification_support` 接收 `run_fn` 参数，首次与二次均调用同一 `run_fn`，确保回传后仍执行选中版本。
- [x] 1.4 生产执行器按 file_path 加载：ComponentLoader 新增 `load_python_component_from_path(file_path)`；**file_path 存相对路径**，加载时基于 PROJECT_ROOT 转为绝对路径（若已为绝对路径则直接使用）；**模块名唯一**：传给 `spec_from_file_location` 的 name 须唯一（如 file_path 哈希或 version_id），避免 sys.modules 缓存污染；加载失败时抛出明确异常（含 version_id、file_path）；缓存 key 使用 file_path（或 version_id），与 `load(component_path)` 的缓存隔离。executor_v2 的 `_load_component_with_version`：**主组件**当 selected_version 非空且 file_path 以 .py 结尾时，调用 `load_python_component_from_path` 构建 component dict（不得调用 `build_component_dict_from_python`）；selected_version 为空时保留 comp_name 回退。`_execute_python_component`：当 component dict 含 `_python_component_class` 时，直接使用该类实例化执行 `run(page)`，不得再调用 adapter 按 comp_name 重新加载。**export 内 component_call 子组件**暂按 adapter 默认加载，不纳入版本管理。
- [x] 1.4.1 **测试接口传逻辑组件名**：版本管理页「开始测试」调用子进程时，test config 的 `component_name` 使用 `version.component_name` 的逻辑部分（如 `miaoshou/login` → `login`），不得使用 `component_path.stem`（如 `login_v1_0_0`），否则 component_loader 按类名约定找不到类，导致「Failed to load Python component」且浏览器未打开。
- [ ] 1.5 回归：对同一 component_name 的多个版本（如 miaoshou/login v1.0.0 与 v1.1.0），分别测试（含验证码回传），验证首次与回传后二次执行均使用对应 version.file_path；生产采集验证稳定版按 file_path 执行。
- [ ] 1.6 **非登录组件测试前登录/复用会话（单组件测试模拟完整链路）**：在 `tools/test_component.py` 的 `_test_python_component_with_browser` 中，对 component_type 为 export、navigation、date_picker、filters 且未 `skip_login` 时：
  - 先尝试通过 `SessionManager` 按 (platform, account_id) 加载已存在的 `storage_state`，若有效则用其创建 context，在该 context 中直接测试当前组件；
  - 若无有效会话，则先执行登录组件——通过 `ComponentVersionService` 选该平台 login 的当前稳定版（`is_stable=True`），按 file_path 加载并通过 `_run_login_with_verification_support` 执行（支持验证码暂停与回传），登录成功后在**同一 browser/context** 中继续执行当前非登录组件；
  - 登录/会话不可用或登录失败时，测试直接失败并给出明确错误（阶段=login 或 session），避免把登录问题误报成导出/导航组件问题。
- [ ] 1.7 **测试环境与生产对齐（会话 + 指纹 + 阶段可观测性）**：在 `_test_python_component_with_browser` 建浏览器 context 时，与 `CollectionExecutorV2.execute` 完全对齐：
  - 使用 `SessionManager.load_session` 得到 `storage_state` + `DeviceFingerprintManager` 得到指纹，`browser.new_context(storage_state=..., **fp_options)`，不使用 `launch_persistent_context`；
  - account_id 缺失时测试失败并明确报错，强制用户选择账号；一账号一指纹、持久会话策略与生产一致；
  - 在进度 / 结果结构中区分「login 阶段」与「export/navigation 等业务阶段」，例如 `phase: "login"` / `phase: "export"`，失败时在前端弹窗中显示是哪一阶段、哪个组件（如 `miaoshou/login v1.0.0` 或 `miaoshou/orders_export v1.0.0`）导致测试失败，便于快速定位问题。
 - [ ] 1.8 **发现模式组件（date_picker / filters）的测试策略**：
   - 组件按两类区分：**可独立测试组件**（login/navigation/export 等，或带完整测试场景描述的组件）与 **仅在完整采集链路中验证的组件**（多数发现模式的日期/筛选控件）。
   - 为发现模式组件新增可选元数据（如 `test_mode`、`test_config`）：`test_mode=flow_only` 表示仅通过 `CollectionExecutorV2.execute` 的完整「登录→导航→日期/筛选→导出」任务进行验证，版本管理页不提供单独「测试组件」按钮；`test_mode=standalone` 且提供 `test_config` 时，允许单组件测试：
     - `test_config.url`：测试时应导航到的页面 URL；
     - `test_config.pre_steps`：在执行组件前需要完成的页面准备步骤（如打开筛选抽屉、切换 Tab）；
     - `test_config.assertions`：执行后需要满足的断言（如表格存在、结果条数/日期范围合理）。
   - 单组件测试工具在检测到 `test_mode=standalone` + 有效 `test_config` 时，先按 `url + pre_steps` 构造上下文，再执行 date_picker/filters 组件；否则仅在完整采集任务中对这些组件做集成级验证。

## 2. 验证码步骤 unconditional 暂停（P0）

- [x] 2.1 生成器修改：在 `backend/services/steps_to_python.py` 中，对图形验证码步骤（step_group 或 scene_tags 含 captcha/captcha_graphical/graphical_captcha），生成「固定短等待 1s → 截图 → raise VerificationRequiredError」，移除 `if await _cap_inp.count() > 0`、`is_visible()` 判断及 `except Exception: pass`。
- [x] 2.2 已存在组件：对迁移后仍保留的需验证码登录组件（如 login.py 等标准化命名的组件）将验证码块改为 unconditional；或在迁移完成后统一处理；若旧文件已删除则 2.2 无对象可改。
- [x] 2.3 文档：在 `docs/guides/RECORDER_PYTHON_OUTPUT.md` 说明「图形验证码步骤为必选暂停，不做条件检测」。

## 3. 删除规则放宽（P1）

- [x] 3.1 后端：`DELETE /component-versions/{version_id}` 可删除条件调整为 `!is_testing && !is_active`，不再要求 `!is_stable`。
- [x] 3.2 前端：删除按钮显示条件 `!row.is_testing && !row.is_active`。
- [x] 3.3 可选：删除稳定版时若存在同组件其他版本，提示是否将另一版本提升为稳定版。
- [x] 3.4 多稳定版一致性：提升某版本为稳定时，自动取消同 component_name 下其他版本的 is_stable；**选版优先级**：ComponentVersionService 若遇历史多稳定版，按 `updated_at DESC` 取最新版本；**提升稳定**接口在「取消其他 is_stable + 设置当前 is_stable」时使用事务或行级锁（如 `SELECT ... FOR UPDATE`），避免并发提升。

## 4. 组件版本管理体验（P1）

- [x] 4.1 实际执行文件展示：在版本列表增加「实际执行文件」列（file_path）；测试弹窗顶部显式展示 file_path。
- [x] 4.2 同平台同类型多稳定版冲突提示：当同一 platform 下同一 component_type 存在多个 is_stable=True 时，在 UI 标出冲突或警告。
- [x] 4.3 组件类型标签：在列表中用标签/颜色区分 login / navigation / export 等类型。

## 5. 前端页面结构（P2，可选）

- [x] 5.1 Tab 概览：统计卡片、最近活动、冲突告警、快速入口（去录制、批量注册）。
- [x] 5.2 Tab 按平台：树形/分组浏览 platform → component_type → 组件，展示当前生产版本。
- [x] 5.3 Tab 全部版本：保留现有表格为「全部版本」Tab，确保列含「实际执行文件」。
- [x] 5.4 **优化**：移除「概览」「按平台」两个 Tab，仅保留「全部版本」列表；筛选框增加 min-width 便于看清已选；筛选为空时与后端一致（全选）。

## 6. 验收与文档

- [ ] 6.1 验收：选择某组件版本测试，确认执行的是该 version.file_path 对应文件且验证码会暂停；禁用后确认可删除；验证码回传后流程正确继续；录制保存创建新版本而非新 component_name；测试 export 等非登录组件时先自动登录或复用会话，且测试使用与生产一致的会话与指纹策略。
- [x] 6.2 更新 CHANGELOG 或相关文档，记录「组件版本测试执行一致性」「删除规则」「验证码必选暂停」「实际执行文件展示」等变更。
- [x] 6.3 部署检查：确认采集环境（backend、collection 容器、本地）均已配置 PROJECT_ROOT；持久会话/指纹使用处已配置 DATA_DIR（或等效）；design 中「采集环境部署检查清单」已纳入运维文档。
