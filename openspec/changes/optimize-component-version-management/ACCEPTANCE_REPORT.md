# optimize-component-version-management 验收报告

**验收时间**：2026-03-14（基于代码与单测的静态验收 + 自动化测试 + 前端联调反馈）

---

## 一、待办与进度总览

| 任务 | 状态 | 验收方式 |
|------|------|----------|
| 0.1～0.6 | 已完成 | 代码已实现（component_name 标准化、录制保存新版本、批量注册、迁移、前端 data_domain、测试传逻辑组件名） |
| 1.1～1.4, 1.4.1 | 已完成 | 代码 + 单测通过（适配器 override、executor 按 file_path 加载、测试注入 component_class） |
| 1.5 | 未完成 | 需人工/E2E：多版本分别测试、验证码回传、生产稳定版按 file_path |
| 1.6 | 未完成 | 代码未实现：非登录组件测试前未先登录/复用会话 |
| 1.7 | 未完成 | 部分实现：test_component 使用 launch_persistent_context，未与 executor_v2 对齐为 new_context(storage_state + 指纹) |
| 1.8 | 未完成 | 代码未实现：date_picker/filters 的 test_mode、test_config |
| 1.9 | 未完成 | 新增阻断：file_path 导入后类发现依赖命名猜测，历史类名（如 MiaoshouMiaoshouLogin）导致 `Failed to load Python component: login` |
| 1.10 | 未完成 | file_path 安全边界校验未落地（越界路径拒绝与错误可观测） |
| 2.x, 3.x, 5.x | 已完成 | 生成器/删除规则/UI单Tab已实现 |
| 4.1, 4.3 | 已完成 | 实际执行文件展示、类型标签已实现 |
| 4.2, 4.4, 4.5, 4.6 | 未完成 | 前端冲突提示、验证码截图URL契约、轮询生命周期、筛选覆盖未完整实现 |
| 6.1 | 未完成 | 综合验收依赖 1.5～1.8 及人工 |
| 6.2, 6.3 | 已完成 | 文档与部署检查已做 |

---

## 二、已验收项（代码 + 单测）

### 1. 生产执行器按 file_path 加载（1.4）

- **component_loader.py**：`load_python_component_from_path(file_path, version_id)` 已实现；相对路径基于 PROJECT_ROOT；唯一模块名（hash+version_id）；缓存 key 为 file_path。
- **executor_v2.py**：`_load_component_with_version` 在 `selected_version.file_path.endswith(".py")` 时调用 `load_python_component_from_path`，返回带 `_python_component_class` 的 dict；`_execute_python_component` 在存在 `_python_component_class` 时直接使用该类执行，不再按 comp_name 加载。
- **单测**：`tests/test_component_loader.py`、`tests/test_executor_v2.py` 共 32 个用例全部通过。

### 2. 测试路径使用选中版本（1.1～1.3, 1.4.1）

- **python_component_adapter.py**：支持 `override_login_class`、`override_navigation_class`、`override_export_class`、`override_date_picker_class`、`override_shop_switch_class`、`override_filters_class`；login/navigation/export 在 override 存在时使用注入类。
- **test_component.py**：`_test_python_component_with_browser` 中按 component_type 注入 override_*_class，适配器使用传入的 component_class 执行。
- **component_versions.py**：启动测试时 `component_name` 使用 `version.component_name.split("/")[-1]`（如 `miaoshou/login` → `login`），满足 1.4.1「传逻辑组件名」要求。

### 3. 删除规则（3.x）

- **component_versions.py**：删除前校验 `!version.is_testing` 且 `!version.is_active`，与提案一致；列表与详情返回 `file_path`、`is_stable`、`is_active`、`is_testing`。

### 4. 版本与文件路径展示（4.x）

- 列表与测试接口中均包含 `file_path` 字段，前端可展示「实际执行文件」。

---

## 三、未实现 / 待人工验证

### 1.5 回归（人工/E2E）

- 同一 component_name 多版本（如 v1.0.0 与 v1.1.0）分别测试时，是否均执行对应 version.file_path（含验证码回传后仍为同一版本）。
- 生产采集是否按稳定版 file_path 执行（需在真实采集环境验证）。

### 1.6 非登录组件测试前登录/复用会话

- **现状**：`test_component.py` 对 export/navigation/date_picker/filters 直接执行组件，未先通过 SessionManager 加载会话或执行 login 稳定版。
- **待做**：在 `_test_python_component_with_browser` 中，对上述类型且未 skip_login 时：先尝试 SessionManager 加载 storage_state；若无则选该平台 login 稳定版按 file_path 执行登录，再在同一 browser/context 执行当前组件。

### 1.7 测试环境与生产对齐

- **现状**：测试工具在「持久化」路径使用 `launch_persistent_context` + SessionManager/DeviceFingerprintManager；非持久化路径为普通 `new_context`，未注入 storage_state 与指纹。
- **待做**：与 executor_v2 一致：`SessionManager.load_session` + `DeviceFingerprintManager`，`browser.new_context(storage_state=..., **fp_options)`；account_id 必填；进度/结果中区分 phase（login / export 等）。

### 1.8 发现模式组件测试策略

- **现状**：未在组件上定义 `test_mode`、`test_config`，版本管理页对所有组件均暴露「测试」按钮。
- **待做**：支持 `test_mode=flow_only`（仅完整采集链路验证）与 `test_mode=standalone` + `test_config`（url、pre_steps、assertions）；单组件测试工具根据元数据决定是否允许单测或仅集成验证。

### 1.9 file_path 导入后类发现稳定性（新增阻断）

- **现状**：测试接口已传逻辑组件名（`miaoshou/login -> login`），并传入 `component_path`；但 `tools/test_component.py` 在按路径导入后仍依赖类名推断。历史版本文件中存在旧命名类（如 `MiaoshouMiaoshouLogin`），与当前推断规则不一致，导致 `Failed to load Python component: login`。
- **影响**：阻断版本管理页「选择账号 -> 开始测试」主路径，属于 P0 验收阻断项。
- **待做**：类发现改为「元数据优先（platform + component_type）+ 命名兜底」，并在失败时输出 `version_id`、`file_path`、候选类列表与匹配规则说明。

### 6.1 综合验收

- 依赖 1.5～1.8 完成或部分完成后的整体回归：版本测试执行 file_path、验证码回传、录制保存新版本、非登录组件先登录/会话、测试环境与生产一致等。

### 前端专项补充（新增）

- **多稳定版冲突提示未落地**：版本列表未看到同平台同逻辑类型多稳定版冲突告警区域或冲突标识。
- **阶段可观测性未落地**：测试失败提示仍以通用错误为主，未稳定展示 `phase + component + version`。
- **验证码截图 URL 契约风险**：截图 URL 组装依赖不稳定对象属性，存在截图无法展示风险。
- **轮询生命周期治理不足**：关闭测试弹窗后轮询不一定停止；轮询异常缺少重试上限和总超时保护，存在后台持续轮询风险。

---

## 四、建议下一步

1. **先做 1.9（P0 阻断）**：修复 file_path 导入后的类发现稳定性，恢复版本管理页测试主路径可用。
2. **并行做 1.10（P0 安全项）**：为 file_path 加载增加目录白名单/越界拒绝，补齐执行链路安全边界。
3. **再做 1.6**：在 test_component 中为非登录组件增加「先会话或先登录再测」逻辑，便于单独测 export/navigation 时不必手动先跑登录。
4. **再做 1.7**：统一测试 context 创建方式与 executor_v2（storage_state + 指纹），并增加 phase 区分，便于排查「登录阶段」与「业务阶段」失败。
5. **补齐 4.2/4.4/4.5/4.6**：前端冲突提示、截图 URL 契约、轮询终止策略、类型筛选覆盖应与提案一致。
6. **1.8 可选**：若 date_picker/filters 目前主要靠完整采集验证，可延后；若需在版本管理页单测这些组件，再上 test_mode/test_config。
7. **1.5 与 6.1**：在 1.9/1.10/1.6/1.7/4.2/4.4/4.5/4.6 落地后做一次人工/E2E 回归（多版本测试、验证码回传、生产稳定版 file_path）。
