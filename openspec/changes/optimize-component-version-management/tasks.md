# Tasks: 采集组件版本管理模块重构

**目标**：组件唯一性（方案 A+C）、修复「测试 A 执行 B」、放宽删除规则、验证码必选暂停，并增强体验（实际执行文件、冲突提示、可选 Tab 结构）。

**验收进度（2026-03-15）**：0.x～5.x、1.6～1.10、4.2、4.4、4.5、4.6、6.2～6.3 已实现并通过代码/单测及专项验收脚本；1.5（多版本回归）与 6.1（综合验收人工部分）待办。实际验收见 `ACCEPTANCE_REPORT.md` 第五节。

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
- [x] 1.6 **非登录组件测试前登录/复用会话（单组件测试模拟完整链路）**：在 `tools/test_component.py` 的 `_test_python_component_with_browser` 中，对 component_type 为 export、navigation、date_picker、filters 且未 `skip_login` 时：
  - 先尝试通过 `SessionManager` 按 (platform, account_id) 加载已存在的 `storage_state`，若有效则用其创建 context，在该 context 中直接测试当前组件；
  - 若无有效会话，则先执行登录组件——通过 `ComponentVersionService` 选该平台 login 的当前稳定版（`is_stable=True`），按 file_path 加载并通过 `_run_login_with_verification_support` 执行（支持验证码暂停与回传），登录成功后在**同一 browser/context** 中继续执行当前非登录组件；
  - 登录/会话不可用或登录失败时，测试直接失败并给出明确错误（阶段=login 或 session），避免把登录问题误报成导出/导航组件问题。
- [x] 1.7 **测试环境与生产对齐（会话 + 指纹 + 阶段可观测性）**：在 `_test_python_component_with_browser` 建浏览器 context 时，与 `CollectionExecutorV2.execute` 完全对齐：
  - 使用 `SessionManager.load_session` 得到 `storage_state` + `DeviceFingerprintManager` 得到指纹，`browser.new_context(storage_state=..., **fp_options)`，不使用 `launch_persistent_context`；
  - account_id 缺失时测试失败并明确报错，强制用户选择账号；一账号一指纹、持久会话策略与生产一致；
  - 在进度 / 结果结构中区分「login 阶段」与「export/navigation 等业务阶段」，例如 `phase: "login"` / `phase: "export"`，失败时在前端弹窗中显示是哪一阶段、哪个组件（如 `miaoshou/login v1.0.0` 或 `miaoshou/orders_export v1.0.0`）导致测试失败，便于快速定位问题。
- [x] 1.8 **发现模式组件（date_picker / filters）的测试策略**：
   - 组件按两类区分：**可独立测试组件**（login/navigation/export 等，或带完整测试场景描述的组件）与 **仅在完整采集链路中验证的组件**（多数发现模式的日期/筛选控件）。
   - 为发现模式组件新增可选元数据（如 `test_mode`、`test_config`）：`test_mode=flow_only` 表示仅通过 `CollectionExecutorV2.execute` 的完整「登录→导航→日期/筛选→导出」任务进行验证，版本管理页不提供单独「测试组件」按钮；`test_mode=standalone` 且提供 `test_config` 时，允许单组件测试：
     - `test_config.url`：测试时应导航到的页面 URL；
     - `test_config.pre_steps`：在执行组件前需要完成的页面准备步骤（如打开筛选抽屉、切换 Tab）；
     - `test_config.assertions`：执行后需要满足的断言（如表格存在、结果条数/日期范围合理）。
   - 单组件测试工具在检测到 `test_mode=standalone` + 有效 `test_config` 时，先按 `url + pre_steps` 构造上下文，再执行 date_picker/filters 组件；否则仅在完整采集任务中对这些组件做集成级验证。
- [x] 1.9 **file_path 导入后类发现稳定性（阻断问题修复）**：
  - 在 `tools/test_component.py`（以及必要时 `component_loader.py`）中，按 `version.file_path` 导入模块后，类发现改为「元数据优先（platform + component_type）+ 命名兜底」；
  - 兼容历史类命名（如 `MiaoshouMiaoshouLogin`），不得仅依赖 `component_name` 推断；
  - 失败时返回可观测错误：包含 `version_id`、`file_path`、候选类列表、匹配规则说明，便于验收阶段快速定位。
- [x] 1.10 **file_path 安全边界校验（P0）**：
  - 在 `component_loader.py` 的 `load_python_component_from_path` 中增加路径安全校验：`realpath(abs_path)` 必须位于允许组件目录（如 `modules/platforms/*/components/`）；
  - 拒绝 `..` 路径穿越、符号链接逃逸与越界路径，不得宽松回退；
  - 失败时错误包含 `version_id`、`file_path`、安全校验失败原因。

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
- [x] 4.4 验证码截图 URL 契约：前端 `getTestVerificationScreenshotUrl` 使用稳定 API base 生成 URL（禁止依赖业务 API 对象上的非标准属性）；`verification_required` 时截图可稳定展示。
- [x] 4.5 测试轮询生命周期治理：测试完成/失败、关闭弹窗、组件卸载时停止轮询；增加连续异常重试上限与整体超时，超过阈值后停止轮询并提示。
- [x] 4.6 组件类型筛选对齐：筛选项与标准化 component_name 规则一致，覆盖 login/navigation/export/date_picker/shop_switch/filters，避免筛选语义偏差。

## 5. 前端页面结构（P2，可选）

- [x] 5.1 Tab 概览：统计卡片、最近活动、冲突告警、快速入口（去录制、批量注册）。（历史方案，已被 5.4 取代）
- [x] 5.2 Tab 按平台：树形/分组浏览 platform → component_type → 组件，展示当前生产版本。（历史方案，已被 5.4 取代）
- [x] 5.3 Tab 全部版本：保留现有表格为「全部版本」Tab，确保列含「实际执行文件」。（作为 5.4 的基础）
- [x] 5.4 **优化（当前生效）**：移除「概览」「按平台」两个 Tab，仅保留「全部版本」列表；筛选框增加 min-width 便于看清已选；筛选为空时与后端一致（全选）。

## 6. 验收与文档

- [ ] 6.1 验收：选择某组件版本测试，确认执行的是该 version.file_path 对应文件且验证码会暂停；禁用后确认可删除；验证码回传后流程正确继续；录制保存创建新版本而非新 component_name；测试 export 等非登录组件时先自动登录或复用会话，且测试使用与生产一致的会话与指纹策略；历史类命名版本（如 `MiaoshouMiaoshouLogin`）可被正确识别执行；失败结果可展示 `phase + component + version`；多稳定版冲突可见且可定位；关闭弹窗或超时后轮询可正确停止；非法 `file_path` 会被安全拒绝且错误可定位。
- [x] 6.2 更新 CHANGELOG 或相关文档，记录「组件版本测试执行一致性」「删除规则」「验证码必选暂停」「实际执行文件展示」等变更。
- [x] 6.3 部署检查：确认采集环境（backend、collection 容器、本地）均已配置 PROJECT_ROOT；持久会话/指纹使用处已配置 DATA_DIR（或等效）；design 中「采集环境部署检查清单」已纳入运维文档。

## 7. 采集脚本现实 Web 稳健性与文档治理（P0/P1）

- [x] 7.1 更新 `docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md`：新增“定位器唯一性契约（strict mode）”“先容器后元素”“禁用 `.first/.nth()` 兜底歧义”“反模式禁用（`count()+is_visible()`、`except Exception: pass`、固定 sleep）”“失败可观测性契约（phase/component/version/url/selector_context）”。
- [x] 7.2 收敛录制与模板文档口径：`RECORDER_PYTHON_OUTPUT.md`、`PYTHON_COMPONENT_TEMPLATE.md`、`COMPONENT_RECORDING_GUIDE.md`、`recording_rules.md` 与新规范一致；历史流程（YAML/Codegen/sync API/UPSERT 旧语义）明确标注为历史或移除。
- [x] 7.3 生成器与静态检查治理（闭环项）：为录制生成代码增加“唯一性与反模式”检查（至少覆盖无注释 `.first/.nth()`、`count()+is_visible()`、`except Exception: pass`、固定 sleep），并完成“提示 + 阻断”的双层治理。
- [x] 7.3.1 提示层：已在生成与停止录制接口返回 lint 提示（warning）用于前端展示与修复引导。
- [x] 7.3.2 阻断层：关键反模式升级为 `error` 且默认阻断保存（可配置白名单/开关），避免高风险代码进入版本库。
- [ ] 7.4 验收补充：新增“重复元素 strict mode”“iframe 重挂载”“SPA 路由局部刷新”“虚拟列表 DOM 复用”四类场景用例，验证脚本在现实 Web 下可稳定执行或可诊断失败。（自动化子集已补，真实页面人工/E2E仍待完成）

## 8. 组件录制生成器合规修复（P0/P1）

- [x] 8.1 去除可选步骤默认吞错：`steps_to_python.py` 生成逻辑中，替换 `except Exception: pass` 为可观测处理（记录步骤上下文并返回结构化错误/可选跳过原因），避免静默继续。
- [x] 8.2 `wait` 动作策略升级：`action=wait` 优先生成条件等待（如 `wait_for(state=...)` / `expect(...).to_be_visible()`）；仅在步骤带显式“固定等待原因”时生成 `wait_for_timeout`，并在注释中保留原因。
- [x] 8.3 作用域收敛生成：为登录表单、对话框、iframe、表格行等常见场景生成“容器 locator + 子元素定位”代码，减少 `page` 根作用域宽匹配。
- [x] 8.4 `.first/.nth` 约束：生成器默认不输出 `.first/.nth`；若必须使用（业务语义确凿），生成注释说明依据并在 lint 中校验“有注释才允许”。
- [x] 8.5 验证码恢复路径治理：`_generate_login_captcha_resume_block` 与 captcha 点击路径移除默认 `.first`，改为唯一性检查 + 失败诊断（phase/component/version/url/selector candidates）。
- [x] 8.6 录制前端 lint 严重级别：`ComponentRecorder.vue` 将 lint 分为 `error`（阻断保存）与 `warning`（可继续），并展示针对性修复建议；关键反模式（吞错、宽泛 `.first`、未说明固定 sleep）默认升为 error（可配置）。
- [x] 8.7（P0）生成接口参数对齐：`/recorder/generate-python` 前端调用补齐 `data_domain` 与 `sub_domain`，与 save 请求体一致，避免 export 子域场景语义漂移。
- [x] 8.8 自动化回归用例：新增生成器回归测试，覆盖四类反模式（`except Exception: pass`、`count()+is_visible()`、无理由固定 sleep、无注释 `.first/.nth`）与四类现实场景（strict mode、iframe 重挂载、SPA 局部刷新、虚拟列表复用）。
- [x] 8.9 可选步骤可观测处理修复：生成器 `optional` 异常块不得引用生成器侧变量（如 `i/action`）导致运行期 NameError；需输出可执行且可诊断的上下文（step_index/action 文本常量）。
- [x] 8.10 lint 与 wait 策略对齐：`wait_for_timeout` 在“显式固定等待原因”存在时不应按 error 阻断保存；无理由固定等待仍保持 error 阻断。
- [x] 8.11 `.first/.nth` 受控放行：实现“有注释说明依据才允许，否则 error 阻断”的 lint 规则，避免一刀切与提案口径不一致。
- [x] 8.12 作用域收敛扩展：在生成器中补齐 iframe、表格行（row）、对话框等场景的容器收敛模板，不仅限登录 form。
- [x] 8.13 lint 门禁一致性补强：`/recorder/save` 必须对“最终写盘代码（含 success_criteria 注入）”执行 lint；注入逻辑不得再引入 `.first/.nth` 或 `count()==0` 绕过阻断层。
- [x] 8.14 login 容器收敛策略修复：生成器不得写死 `get_by_role("form")`；实现“语义容器优先 + 业务容器兜底 + page 根作用域告警兜底”的多候选收敛策略，并在失败时输出容器候选诊断信息。
- [x] 8.15 URL 导航契约落地：为 login 组件生成/模板补齐导航策略（`login_url_override > account.login_url > 平台默认 URL`），并实现导航后双信号确认（URL/路由特征 + 关键元素可见）；新增回归覆盖“未显式 navigate 也能稳定进入登录页或给出可诊断失败”场景。
  - [x] 8.15.1 URL 来源优先级实现：`params.login_url_override > account.login_url > 平台默认 URL`。
  - [x] 8.15.2 导航前判定实现：当前页已满足“目标路由特征 + 关键登录元素可见”时跳过 goto。
  - [x] 8.15.3 导航后双信号判定实现：URL/路由特征 + 关键元素可见，禁止单信号判定。
  - [x] 8.15.4 可观测性补齐：失败返回 `current_url/target_url/phase/component/version/selector_context`。
  - [x] 8.15.5 回归测试补齐：覆盖“缺失 navigate 步骤、容器无 role=form、URL 错配”三类场景。

## 9. 提案关闭门槛（P0）

- [ ] 9.1 不允许归档条件：`1.5`、`6.1`、`7.4` 任一未完成时，变更不得归档（仅可保持进行中）。
- [ ] 9.2 归档前必须通过：关键反模式阻断保存（7.3.2）+ 生成接口参数对齐（8.7）+ 现实 Web 四类补充验收（7.4）。
- [x] 9.3 归档前必须通过：`8.14`（login 容器收敛）与 `8.15`（URL 导航契约）自动化回归与至少 1 组真实页面验收通过。

## 10. 最小上线顺序（执行编排）

- [x] 10.1 S1 止血阶段：优先完成 `8.14`，确保 login 组件在无 `role=form` 页面不再首步失败。
- [x] 10.2 S2 契约阶段：完成 `8.15.1~8.15.4`，使 URL 导航具备来源优先级、导航前判定、导航后双信号与失败可观测性。
- [x] 10.3 S3 质量阶段：完成 `8.15.5` 回归 + 至少 1 组真实页面验收，并同步更新验收报告。
