# 组件版本管理能力（Delta）

## ADDED Requirements

### Requirement: 组件唯一性（方案 A）

系统 SHALL 按 (platform, component_type) 约束逻辑组件唯一性；component_name 标准化为 `{platform}/{component_type}`（login/navigation/date_picker/shop_switch/filters 等）或 `{platform}/{domain}_export`（导出类，含 `{platform}/{domain}_{sub}_export` 子域）；同一平台同一类型只允许一个逻辑组件槽位；禁止存在 miaoshou/login 与 miaoshou/miaoshou_login 并存。date_picker、shop_switch、filters 有独立 component_name 槽位。**子域导出**：有子类型的数据域（如 services 的 agent、ai_assistant）按子类型分别录制/保存，各自对应独立 component_name，不是一个大组件在一次流程中串联导出多种子类型；执行器按子域分别加载对应组件。

#### Scenario: 标准化 component_name

- **WHEN** 录制保存或批量注册组件
- **THEN** component_name 由 platform + component_type（export 需 data_domain）推导
- **AND** 不创建与 component_type 不一致的新 component_name（如禁止 miaoshou/miaoshou_login）

#### Scenario: 多版本同组件

- **WHEN** 同一 component_name 存在多个 version（v1.0.0、v1.1.0）
- **THEN** 生产仅使用 is_stable 版本
- **AND** 测试可针对任意版本执行 version.file_path 对应实现

#### Scenario: 同组件仅一稳定版

- **WHEN** 用户将某版本「提升为稳定版」
- **THEN** 系统自动取消该 component_name 下其他版本的 is_stable
- **AND** 选版时若因历史数据存在多 is_stable，按 `updated_at DESC` 取最新版本作为选版结果，保证生产执行确定性

### Requirement: 录制保存创建新版本（方案 C）

系统 SHALL 在录制保存时「更新该组件」而非新建 component_name；保存行为 = 为该组件创建新版本（patch 递增），写入版本化 file_path（如 login_v1_0_1.py），新版本默认非稳定；取代原 UPSERT（同 file_path 则 UPDATE）语义。**版本号 patch 递增**：在应用层解析 version 为 (major, minor, patch) 元组后取最大值，patch+1；不得依赖 SQL MAX(version) 字典序（否则 1.0.9 > 1.0.10）。

#### Scenario: 保存创建新版本

- **WHEN** 用户在录制结果页保存组件
- **THEN** 系统由 platform + component_type 推导 component_name
- **AND** 创建新版本记录并写入版本化 file_path
- **AND** 新版本默认 is_stable=False，供测试后提升稳定

### Requirement: 生产执行器按 file_path 加载

系统 SHALL 在生产采集时，从 ComponentVersionService 选中版本后，按 selected_version.file_path 加载组件类（使用 importlib.util.spec_from_file_location），不得再按 comp_name 从模块路径加载；测试与生产均按 file_path 执行，确保版本管理的「稳定版」与生产实际一致。**范围**：主组件（login、navigation、export、execution_order 中独立槽位的 date_picker/shop_switch/filters）按 file_path 加载；export 内 component_call 调用的 date_picker、filters、shop_switch 暂按 adapter 默认加载，不纳入本变更；file_path 存相对路径，加载时基于 PROJECT_ROOT 转为绝对路径。

#### Scenario: 执行器按 file_path 加载

- **WHEN** 执行器加载组件用于生产采集
- **THEN** 从版本服务取得 selected_version 的 file_path
- **AND** 通过 file_path 加载组件类，构建 component dict（含 _python_component_class）
- **AND** `_execute_python_component` 当 component dict 含 `_python_component_class` 时直接使用该类实例化执行 run(page)，不得再调用 adapter 按 comp_name 重新加载
- **AND** `load_python_component_from_path` 传给 `spec_from_file_location` 的模块名须唯一（如 file_path 哈希或 version_id），避免 sys.modules 缓存污染

### Requirement: 组件版本删除规则

系统 SHALL 允许用户在组件版本管理界面删除满足条件的组件版本记录，且删除按钮的显示条件与后端校验一致。

#### Scenario: 已禁用版本可删除

- **WHEN** 某组件版本处于已禁用状态（is_active=False）且未处于 A/B 测试中（is_testing=False）
- **THEN** 系统在列表中显示该版本的「删除」按钮
- **AND** 用户点击删除后，后端校验通过并删除该版本记录（及可选地清理仅被该版本引用的 .py 文件）
- **AND** 稳定版（is_stable=True）在禁用后也允许被删除

#### Scenario: 启用中或测试中的版本不可删除

- **WHEN** 某组件版本处于启用状态（is_active=True）或正在 A/B 测试中（is_testing=True）
- **THEN** 系统不显示「删除」按钮或后端拒绝删除请求并返回明确错误信息
- **AND** 删除规则为「可删除 = 非测试中且已禁用」（`!is_testing && !is_active`），启用中的版本无论是否稳定版均不可删除

### Requirement: 组件版本测试执行一致性

系统 SHALL 在用户对某一组件版本发起测试时，实际执行的代码必须来自该版本的 file_path 所指向的 Python 文件，不得执行同平台其他文件中的同名类型组件。

#### Scenario: 测试选中版本即执行该版本

- **WHEN** 用户在组件版本管理页对版本 A（如 miaoshou/login v1.0.0，file_path 指向 login_v1_0_0.py）点击「测试」
- **THEN** 系统根据 version.file_path 加载对应的 .py 文件并得到组件类
- **AND** 执行测试时使用该类（或通过适配器注入该类）运行 run(page)，而非按 component_type 再加载其他模块（如 login.py）
- **AND** 若涉及验证码回传，适配器在 override 存在时必须使用注入类；或改造验证码恢复路径为首次与二次均调用同一 run_fn，确保回传后仍使用同一组件类（不得回退到按模块名加载的其他实现）
- **AND** 测试结果与用户选中的版本一一对应，避免「测试 A 组件却执行 B 组件」

#### Scenario: 测试结果可区分实际执行文件

- **WHEN** 测试完成或进行中
- **THEN** 系统在进度或结果中可展示或返回实际执行的组件文件路径或类名，便于用户确认

### Requirement: file_path 导入后的类入口稳定发现

系统 SHALL 在按 `version.file_path` 导入 Python 模块后，使用稳定的组件类发现策略，优先基于类元数据（platform、component_type）匹配，再回退命名约定，兼容历史类命名，避免因类名风格差异导致测试阻断。

#### Scenario: 历史类命名可被正确识别

- **WHEN** 版本文件已按 `file_path` 导入，但模块内类名不符合当前命名约定（如 `MiaoshouMiaoshouLogin`）
- **THEN** 系统仍能通过元数据匹配到目标组件类并执行测试
- **AND** 不得仅依赖 `component_name -> 类名` 的字符串推断

#### Scenario: 类发现失败时错误可观测

- **WHEN** 导入模块后仍无法匹配到目标组件类
- **THEN** 错误信息包含 `version_id`、`file_path`、模块候选类列表与匹配规则说明
- **AND** 前端可展示明确可定位的失败原因，而非仅显示通用失败文案

### Requirement: file_path 加载安全边界

系统 SHALL 对 `version.file_path` 的加载路径进行安全边界控制：归一化后的绝对路径必须位于允许的组件目录内，禁止路径穿越与越界加载，防止加载任意非组件文件。

#### Scenario: 合法组件路径可加载

- **WHEN** `file_path` 归一化后位于允许目录（如 `modules/platforms/*/components/`）
- **THEN** 系统允许继续加载并执行组件

#### Scenario: 非法路径被拒绝

- **WHEN** `file_path` 含 `..`、符号链接逃逸或归一化后越界到允许目录之外
- **THEN** 系统拒绝加载并返回明确错误
- **AND** 错误信息包含 `version_id`、`file_path` 与安全校验失败原因

### Requirement: 组件测试环境与生产对齐

系统 SHALL 使组件测试环境与生产采集一致：一账号对应一个浏览器指纹与持久会话；测试非登录组件（export、navigation、date_picker、filters）前必须先完成自动登录或复用该账号持久会话，未提供 skip_login 且登录/会话不可用时不得执行该组件测试。

#### Scenario: 非登录组件测试前登录或复用会话

- **WHEN** 用户对 export、navigation、date_picker 或 filters 组件发起测试且未选择跳过登录
- **THEN** 系统先尝试加载该账号的持久会话（SessionManager）；若有有效会话则用其建 context 并继续执行目标组件
- **AND** 若无有效会话则先执行登录组件——通过 ComponentVersionService 选该平台 login 的**当前稳定版**（is_stable=True），按 file_path 加载（支持验证码暂停与回传），登录成功后再执行目标组件
- **AND** 登录或会话不可用时测试失败并返回明确错误，不执行目标组件

#### Scenario: 测试使用与生产一致的会话与指纹

- **WHEN** 组件测试启动浏览器 context
- **THEN** 系统按 account_id 使用 SessionManager.load_session 得到 storage_state 与 DeviceFingerprintManager 得到指纹，`new_context(storage_state=..., **fp_options)`（与 executor_v2 完全相同，不使用 launch_persistent_context）
- **AND** 一账号一指纹、持久会话，尽可能与真实采集环境一致，避免测试通过而生产失败或反之

#### Scenario: account_id 缺失时测试失败

- **WHEN** 用户发起组件测试且 account_id 缺失或未选择账号
- **THEN** 系统拒绝执行测试并返回明确错误，强制用户选择账号
- **AND** 非登录组件测试依赖 account_id 加载会话/指纹，缺失则无法与生产对齐

### Requirement: 前端冲突提示与测试可观测性

系统 SHALL 在组件版本管理前端提供与版本治理一致的可观测性能力，包括多稳定版冲突提示、阶段化失败信息展示、验证码截图可访问与轮询生命周期治理，避免出现“状态不明”或“无限轮询”等历史问题。

#### Scenario: 多稳定版冲突可见

- **WHEN** 同一平台同一逻辑类型存在多个稳定版
- **THEN** 前端在列表页显式显示冲突提示
- **AND** 提示中包含平台、逻辑类型与冲突版本标识，便于用户处理

#### Scenario: 失败阶段与组件版本可定位

- **WHEN** 组件测试失败（包括 session/login/业务阶段）
- **THEN** 状态接口或结果对象包含 `phase`、`phase_component_name`、`phase_component_version`
- **AND** 前端在失败文案或详情区展示上述字段，不得仅显示通用错误文案

#### Scenario: 验证码截图 URL 可稳定访问

- **WHEN** 测试状态为 `verification_required`
- **THEN** 前端使用统一 API base 规则构造验证码截图 URL
- **AND** 验证码截图可在测试弹窗中稳定展示，不依赖不确定对象属性拼接路径

#### Scenario: 轮询具备终止与保护机制

- **WHEN** 测试轮询进行中
- **THEN** 在 `completed`、`failed`、关闭测试弹窗、组件卸载时停止轮询
- **AND** 连续异常达到阈值或超过总超时后停止轮询并提示用户
