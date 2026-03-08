# Design: 采集组件版本管理模块重构

## Context

- 录制器已产出符合规范的 Python 组件，组件版本管理页是「测试 → 选版 → 生产」的关键环节。
- 当前测试路径使用 `adapter.login()` 等按模块名加载，与 `version.file_path` 脱节，导致「测 A 执行 B」。
- 删除规则过严、验证码静默穿透、缺少「实际执行文件」展示，易造成混淆与误操作。
- 需按业界主流实践重新设计，而非延续旧设计修补。

## 业界主流实践参考

| 来源 | 核心能力 | 借鉴点 |
|------|----------|--------|
| Polyaxon Component Hub | 多版本、stage、运行引用 | 组件 = 可执行实体，版本 = tag，运行指定 `org/component:v1.1` |
| Mendix Marketplace | Releases  tab、Download、Manage Versions | 版本列表、操作入口、详情分 Tab |
| n8n Node Versioning | 新流程用最新、老流程锁版本 | 版本与执行明确绑定 |
| ScriptRunner Registry | 集中注册、按功能分组、可搜 | 按能力组织、快速定位 |
| Apicurio Registry | Dashboard 概览、版本 diff | 统计卡片、版本对比 |
| OpCon / MicroFocus | 启用/禁用、部署、回滚 | 删除规则、部署语义 |

共识：**版本与执行明确绑定**、**实际执行文件可见**、**删除/启用规则清晰**、**执行结果可追溯**。

## 组件唯一性与更新工作流（方案 A + C）

### 组件唯一性（方案 A）

- **逻辑组件**：按 `(platform, component_type)` 唯一，同一平台同一类型只允许一个逻辑组件槽位。
- **component_name 标准化**：
  - login / navigation / shop_switch / date_picker / filters：`{platform}/{component_type}`，如 `miaoshou/login`、`miaoshou/date_picker`。date_picker、shop_switch、filters 有独立 component_name 槽位，可单独录制与版本管理。
  - export：`{platform}/{domain}_export` 或 `{platform}/{domain}_{sub}_export`，如 `miaoshou/orders_export`
- **带子域数据域的导出策略**：有子类型的数据域（如 services 的 agent、ai_assistant）按**子类型分别导出**，不是一个大组件在一次流程中串联导出多种子类型。每个子域对应独立 component_name（如 `miaoshou/services_agent_export`、`miaoshou/services_ai_assistant_export`），各自录制、各自保存、各自测试；执行器按子域分别加载并执行。`{platform}/{domain}_export` 仅用于无子域或子域组件缺失时的回退。
- **多版本**：同一 component_name 可有多个 version（v1.0.0、v1.1.0）；生产仅使用 is_stable 版本。
- **约束**：禁止同一 (platform, component_type) 下存在多个 component_name（如 miaoshou/login 与 miaoshou/miaoshou_login 并存）；批量注册与录制保存均按标准化 component_name 操作。

### 录制保存行为（方案 C）

- 录制保存时**更新已有组件**，不新建 component_name。
- 保存 = 为该组件创建**新版本**（如 v1.1.0），写入对应 file_path，新版本默认**非稳定**。
- 用户选择「更新哪个组件」：由 platform + component_type（录制时已知）推导 component_name。**请求体**：`RecorderSaveRequest` 与 `GeneratePythonRequest` 必须包含 `platform`、`component_type`；export 时必须包含 `data_domain`（来源：录制会话或前端选择）；带子域的 export（如 services:agent）还需包含 `sub_domain`，推导为 `{platform}/{domain}_{sub}_export`。component_name = `{platform}/{component_type}`、`{platform}/{domain}_export` 或 `{platform}/{domain}_{sub}_export`。**校验**：export 时 data_domain 缺失则后端返回 400 并明确报错；当 data_domain 有子类型且前端选择子域导出时，sub_domain 必填，否则 400。**sub_domain 子类型判定**：后端维护「有子类型的数据域」配置（如 `DATA_DOMAIN_SUB_TYPES = {"services": ["agent", "ai_assistant"]}`），硬编码或配置化；仅当 data_domain 在此配置中且请求体含 sub_domain 或前端选择子域导出时，校验 sub_domain 必填。**generate-python**：`POST /recorder/generate-python` 请求体与 save 对齐，增加 data_domain、sub_domain，使用相同推导规则（platform+component_type+data_domain+sub_domain），component_name 由后端推导，不再必填或废弃。
- 若该 component_name 尚不存在（首次录制），则创建首版本（v1.0.0），遵循「新版本默认非稳定」即 is_stable=False，用户测试通过后可手动提升为稳定。

### 版本工作流

1. **保存** → 新版本（草稿）
2. **测试** → 在版本管理中选中该版本，执行 `version.file_path` 对应实现
3. **提升稳定** → 测试通过后，将该版本设为 is_stable，取消同组件其他稳定版
4. **生产** → 执行器通过 ComponentVersionService 选 stable 版本，按 file_path 加载

### 文件存储策略

- **版本化文件名**：使用 Python 模块名安全格式，如 `login_v1_1_0.py`（版本号中的 `.` 替换为 `_`），避免 `importlib` 加载时报错。
- **file_path 存储规范**：DB 中 ComponentVersion.file_path 统一存**相对路径**（相对于 PROJECT_ROOT），如 `miaoshou/components/login_v1_1_0.py`；加载时通过 PROJECT_ROOT + file_path 转为绝对路径再传给 `importlib.util.spec_from_file_location`。不同部署环境 PROJECT_ROOT 可不同（Docker 内 `/app`，本地为仓库根），保证跨环境一致。
- **加载方式**：通过 `importlib.util.spec_from_file_location` 从绝对路径加载，不依赖 `import_module(module_path)`。
- **备选**：主文件 + 草稿（`login.py` + `login_draft.py`），提升稳定时草稿覆盖主文件；回滚依赖 Git。

### component_type 从 component_name 推导

- 用于筛选、冲突检测、按平台分组。规则：`{platform}/login` → login；`{platform}/navigation` → navigation；`{platform}/*_export` → export；`{platform}/date_picker` → date_picker；`{platform}/shop_switch` → shop_switch。可选在 ComponentVersion 增加 component_type 冗余字段以简化查询。

### 版本号递增

- 录制保存时：patch 递增（1.0.0 → 1.0.1）。若需 minor 递增，可后续扩展。
- **语义版本解析**：不得依赖 SQL `MAX(version)` 字典序（否则 `1.0.9` > `1.0.10`）。应在应用层解析 version 为 (major, minor, patch) 元组，取最大值后 patch+1，或增加 version_sort_key 字段。实现时：查询该 component_name 所有版本，解析为元组排序取 max，再递增。
- **并发保存**：同一 component_name 并发保存时，版本号需避免冲突。采用「应用层解析取最大版本 + 1」或「唯一约束 (component_name, version) + 冲突时重试」；实施时在保存事务内解析当前最大版本再插入，或捕获 IntegrityError 后重试。
- 与 add-collection-recorder 的 UPSERT 冲突：方案 C 取代「同 file_path 则 UPDATE」；每次保存创建新版本 + 新 file_path，不再 overwrite 同文件。

## Goals / Non-Goals

- **Goals**：组件唯一性按 (platform, component_type)；录制保存更新已有组件并创建新版本；测试执行与选中版本一致；已禁用版本可删除；验证码步骤到达即暂停；列表与测试弹窗展示实际执行文件；同平台同类型多稳定版冲突提示；可选按平台分组浏览；**组件测试环境与生产对齐**（非登录组件测试前自动登录或复用会话，一账号一指纹与持久会话）。
- **Non-Goals**：不改变生产执行器选版逻辑（仍按 ComponentVersionService）；不实现验证码自动打码；不在此变更中实现完整「按平台」树形浏览（可列为后续迭代）。

## 目标功能集

### 必须

- 组件/版本浏览（平台、类型、状态筛选）
- 测试时执行 `version.file_path` 对应实现
- 验证码回传（图形验证码截图 + 输入、OTP 输入）
- 删除规则：`!is_testing && !is_active` 可删
- 列表与测试弹窗展示「实际执行文件」
- **测试环境与生产对齐**：非登录组件（export/navigation/date_picker/filters）测试前自动登录或复用该账号持久会话；测试使用与 executor_v2 相同的「按 account_id 的 SessionManager + DeviceFingerprintManager」建 context，一账号一指纹、持久会话，追求与真实采集一致

### 强烈建议

- 同平台同类型多稳定版冲突提示
- 组件类型标签（login/navigation/export 等）

### 后续迭代

- Tab「概览」Dashboard
- Tab「按平台」树形浏览
- 版本详情侧栏、最近 N 次测试历史

## 前端页面结构

### 布局

```
+------------------------------------------------------------------+
|  采集组件库                                                        |
+------------------------------------------------------------------+
|  [概览] [按平台] [全部版本]  |  筛选: 平台 | 类型 | 状态 | [批量注册] |
+------------------------------------------------------------------+
|                        主内容区                                    |
+------------------------------------------------------------------+
```

- **Tab 概览**（可选）：统计卡片、最近活动、冲突告警、快速入口
- **Tab 按平台**（可选）：树形 platform → component_type → 组件，展示「当前生产」版本
- **Tab 全部版本**（必须）：表格，列含「实际执行文件」、状态、成功率、操作

### 测试弹窗

- 顶部显式展示：**组件名、版本号、实际执行文件路径**
- 验证码：图形验证码展示截图 + 输入框；OTP 仅输入框
- 进度：步骤级日志、成功/失败结果

## Decisions

### 1. 测试时执行哪个组件类

- **决策**：测试路径必须使用从 `version.file_path` 加载到的组件类执行，而非适配器按 component_type 再按模块名加载。所有 component_type（login、navigation、export、date_picker、shop_switch、filters）均须支持注入；若版本管理可测试 shop_switch、filters，适配器亦需 override_shop_switch_class、override_filters_class 等参数。
- **验证码恢复路径**：`adapter.login()` 内部在有 `override_login_class` 时必须使用注入类执行；若适配器未正确使用 override，则改造 `_run_login_with_verification_support` 接收 `run_fn` 参数，首次与二次均调用同一 `run_fn`，确保回传后仍执行选中版本。
- **实现**：采用适配器注入方案 `create_adapter(..., override_login_class=component_class)`；适配器 `login()` 方法在 override 存在时直接用 `override_login_class(page)`，不得再调用 `_load_component_class("login")`。

### 2. 删除条件

- **决策**：可删除 = `!is_testing && !is_active`。批量注册的稳定版禁用后也可删除。启用中的版本不可删除。

### 3. 验证码步骤生成语义

- **决策**：图形验证码步骤生成「到达即等待 1s → 截图 → raise VerificationRequiredError」，不生成 `count()>0` / `is_visible()` 及 `except Exception: pass`。
- **注意**：若某平台存在「有时无验证码」登录页，可后续通过可选验证码步骤单独支持；本变更统一为必选暂停。

### 5. 多稳定版冲突

- **决策**：「提升稳定」时自动取消同组件（同一 component_name）下其他版本的 is_stable，保证同一时刻同组件仅有一个 is_stable。**选版优先级**：若因历史数据存在多 is_stable，ComponentVersionService 按 `updated_at DESC` 取最新版本作为选版结果，保证生产执行确定性。
- **并发**：「提升稳定」需在同一 component_name 下做互斥：在「取消其他 is_stable + 设置当前 is_stable」的更新中使用**事务**或**行级锁**（如 `SELECT ... FOR UPDATE`），避免并发提升导致同组件存在多个 is_stable。

### 4. 生产执行器按 file_path 加载

- **决策**：executor_v2 的 `_load_component_with_version` 在取得 selected_version 后，必须按 `selected_version.file_path` 加载组件类，不得再使用 comp_name 调用 `build_component_dict_from_python`。**执行链路**：当 component dict 含 `_python_component_class`（由 file_path 加载）时，`_execute_python_component` 应直接使用该类实例化执行 `run(page)`，不得再调用 adapter 按 comp_name 重新加载。
- **主组件与子组件范围**：本变更主组件（login、navigation、export、及 execution_order 中独立槽位的 date_picker、shop_switch、filters）按 `selected_version.file_path` 加载；**export 内 component_call 调用的 date_picker、filters、shop_switch** 暂按 adapter 默认 `_load_component_class(comp_name)` 加载，不纳入本变更版本管理；后续迭代可扩展子组件按版本加载。
- **Fallback**：当 `selected_version is None`（版本服务不可用、无稳定版、无活跃版本）时，**保留 comp_name 回退**：调用 `build_component_dict_from_python(platform, comp_name, params)`，依赖标准化命名主文件（如 login.py），与现有降级逻辑一致，保证采集在异常情况下仍能执行。
- **实现**：ComponentLoader 新增 `load_python_component_from_path(file_path: str) -> Type`；若 file_path 已为绝对路径则直接使用，否则基于 project_root 转为绝对路径再传给 `importlib.util.spec_from_file_location`；**模块名唯一**：传给 `spec_from_file_location` 的 name 须唯一（如使用 file_path 哈希或 version_id），避免不同 file_path 使用相同模块名导致 sys.modules 缓存污染；加载失败时抛出明确异常（含 version_id、file_path 便于排查）。该方法的缓存 key 使用 file_path（或 version_id），与现有 `load(component_path)` 的缓存隔离，避免多版本共用或错误命中。

### 6. 组件测试环境与生产对齐

- **决策**：组件测试（含版本管理发起的测试）应与生产采集一致：一账号对应一个浏览器指纹与持久会话；非登录组件测试前必须先完成自动登录或复用该账号持久会话（未 skip_login 时），登录/会话不可用则不得执行该组件测试。
- **非登录组件测试前的登录版本**：自动登录应使用该平台 login 的**当前稳定版**（is_stable=True），按 file_path 加载，与生产执行一致。
- **实现**：在 `tools/test_component.py` 的 **Python 组件测试路径**（`_test_python_component_with_browser`）中：（1）account_id 缺失时测试失败并明确报错，强制用户选择账号；（2）对 export、navigation、date_picker、filters，在执行该组件前先执行自动登录或按 account_id 加载 SessionManager 会话；若无有效 storage_state 则先执行登录组件——**通过 ComponentVersionService 选该平台 login 的稳定版，按 file_path 加载**，再继续；（3）建 context 时与 executor_v2 完全相同：使用 `SessionManager.load_session` 得到 storage_state + `DeviceFingerprintManager` 得到指纹选项，`new_context(storage_state=..., **fp_options)`，不使用 launch_persistent_context，保证与真实采集环境一致。

## Risks / Trade-offs

- **适配器注入**：增加可选参数后，生产路径不传入 override，默认行为不变。
- **删除稳定版**：放宽后用户可能误删唯一稳定版；通过「可删 = 已禁用」降低风险（禁用即「不用」，删除前需先禁用）。
- **验证码「有时无验证码」**：本变更将图形验证码步骤统一为必选暂停，不处理「有时出现、有时不出现」验证码的登录页；该场景列为后续迭代（如 optional 验证码步骤或条件分支）。
- **file_path 文件不存在**：DB 中 file_path 指向已删除/回滚的文件时，加载会失败；需抛出明确异常（含 version_id、file_path），便于运维排查；部署时需保证代码与 DB 版本表一致。

## Migration Plan

1. **删除旧组件，避免误用**：迁移脚本**删除** ComponentVersion 表中所有不符合标准化 component_name 规则的记录（如 miaoshou/miaoshou_login、以及任何与 `{platform}/{type}` 或 `{platform}/{domain}_export` 不一致的 component_name）；**关联表处理**：删除前先处理 ComponentTestHistory——删除 `version_id` 指向待删 ComponentVersion id 的记录，或将 `version_id` 置 NULL，再删除 ComponentVersion；两种策略择一（推荐删除子记录以保证数据一致性）。**文件策略**：删除或归档非标准化旧 .py 文件（如 miaoshou_login.py）；**保留**标准化命名的主文件（如 login.py、navigation.py、orders_export.py）作为 fallback，供无版本记录时 `build_component_dict_from_python(platform, comp_name)` 加载，避免 fallback 路径 FileNotFoundError。采集模块完全重构完毕后将**重新录制**并写入新版本。**删除后行为**：若某 component_name 无版本记录，生产采集依赖 fallback 按 comp_name 加载标准化主文件，直至重新录制并写入新版本。
2. **execution_order 与平台配置**：`execution_order.py` 默认使用类型名（login、export 等），通常无需改动；若有平台覆盖（`_PLATFORM_ORDER`）或平台执行顺序配置中使用了旧 comp_name（如 miaoshou_login），迁移时改为标准化名称（如 `login`），保证执行器构造的 component_name 与未来新录制一致。
3. **验证码**（后）：迁移完成后，若仍有保留的 .py 文件需验证码，按 2.2 改验证码块为 unconditional；否则随旧文件一并删除或归档。
4. **component_name 校验**：录制保存、批量注册、版本管理新增 component_name 时，校验其符合 `{platform}/{type}` 或 `{platform}/{domain}_export` 规则，禁止再次录入旧格式，从源头避免误用。
5. **回滚**：若需回滚，需先恢复 ComponentVersion 表备份、恢复 execution_order 配置；若已删除 .py 文件，需从 Git 或归档恢复。

6. **执行时机**：迁移脚本（0.5）应在 0.2 录制保存逻辑上线且 component_name 校验生效后执行；或按 tasks 顺序（0 → 1 → 2 → 3...）在 0.4 完成后、用户确认可重新录制前执行。

## 采集环境部署检查清单

所有采集执行环境（主栈 backend 容器、独立 collection 容器、本地 `run.py --local`）需满足：

- **PROJECT_ROOT**：必须设置，供 `load_python_component_from_path` 将 DB 中相对 file_path 转为绝对路径。Docker 内通常为 `/app`，本地为仓库根路径。DB 中 file_path 存相对路径，加载时 `abs_path = os.path.join(PROJECT_ROOT, file_path)`。
- **DATA_DIR**（或等效配置）：采集需持久会话与指纹时，需正确配置以支持 SessionManager、DeviceFingerprintManager 的存储路径；`docker-compose.collection.yml` 已通过 volumes 配置 `collection_browser_data`、`collection_fingerprints`。

## Open Questions

- 无；生产执行器按 file_path 加载已纳入本变更 P0 范围。
