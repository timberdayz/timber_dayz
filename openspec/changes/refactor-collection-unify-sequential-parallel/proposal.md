# Change: 采集执行器修复与采集架构简化

## 当前实现状态（避免重复工作）

- **Phase 1（止血 + 双轨统一）**：**已完成**。
  - P0 认证：`backend/routers/auth.py` 的 `get_current_user` 已改为在所有失败分支 `raise HTTPException(401/403)`，不再返回 `error_response`。
  - P0 顺序路径：`executor_v2._execute_with_python_components` 已使用 `create_adapter(platform=..., account=..., config=params)`，`adapter.export(page=page, data_domain=domain)`，download_dir 从 `config['task']['download_dir']` 读取。
  - P0 并行路径：`execute_parallel_domains` 已改为使用 `create_adapter` + `adapter.login` / `adapter.export`，与顺序路径同一套组件执行模型；`_execute_single_domain_parallel` 使用 `create_adapter` + `adapter.export`。
  - P1：`_execute_collection_task_background` 已移除 `db_session_maker` 参数，路由调用处未再传入。
  - **未做**：并行模式尚未支持 `sub_domains` 参数（顺序模式已支持）；若需并行子域，需为 `execute_parallel_domains` 增加 `sub_domains` 并在路由传入。
- **Phase 2（CollectionRunner + 脚本约定发现）**：**未实施**。当前路由仍调用 `CollectionExecutorV2.execute` / `execute_parallel_domains`，未引入 `CollectionRunner`，未切换至约定目录脚本发现，`PythonComponentAdapter` / YAML 引擎仍在使用中。

## Why

1. **顺序路径当前不可用**：`_execute_with_python_components` 中调用 `create_adapter(..., params=..., download_dir=...)`，而 `create_adapter` 与 `PythonComponentAdapter` 的签名仅有 `platform, account, config, ...`，导致 `TypeError: create_adapter() got an unexpected keyword argument 'params'`，有头/无头采集均无法执行。
2. **认证依赖返回 Response 导致 500**：`get_current_user` 在未认证或校验失败时 `return error_response(...)`（JSONResponse），被 FastAPI 注入为 `current_user`，导致依赖该依赖的路由出现 `'JSONResponse' object has no attribute 'user_id'`，且限流/性能中间件报错。
3. **顺序与并行双轨维护**：顺序路径使用 Python 组件 + `create_adapter` + `adapter.login` / `adapter.export`；并行路径使用 `component_loader.load` + `_execute_component` / `_execute_export_component`（YAML 配置字典）。两套执行模型行为可能不一致，扩展与排错需维护两处，期望**行为一致、避免双轨维护**。
4. **冗余参数**：`_execute_collection_task_background` 接收 `db_session_maker` 但从未使用，易误导后续维护。
5. **执行器过度承载、双套适配层**：`CollectionExecutorV2` 约 2880 行，同时承担流程编排、浏览器生命周期、YAML 步骤引擎、Python 组件分发、文件处理、版本管理等职责；且项目中存在 `PythonComponentAdapter`（executor 在用）与 `PlatformAdapter`（`modules/platforms/*/adapter.py`，已提供 `login()` / `orders_export()` 等工厂但**从未被执行器使用**），导致两套适配层并存。按官方与业界常见做法，宜引入**薄调度层 + 单一组件入口**，简化架构。

## What Changes

**推进策略**：分两阶段。**Phase 1** 先止血（P0 认证 + create_adapter/export 参数修复 + P1 db_session_maker），使顺序/并行在现有架构下可跑通；**Phase 2** 引入薄调度层与单一组件入口，简化架构并废弃冗余代码。

### 1. P0：认证依赖改为抛出 HTTPException（Phase 1）

- **位置**：`backend/routers/auth.py`，`get_current_user`。
- **修改**：所有「未提供 token / token 无效 / 用户不存在或禁用 / 账号被暂停」分支，由 `return error_response(...)` 改为 `raise HTTPException(status_code=401 或 403, detail="...")`。统一错误体格式由现有基础设施保证：`backend/main.py` 已注册 `HTTPException` 的 `exception_handler`，会将其转为与 `error_response` 一致的响应结构；无需新增 handler，仅需确认 401/403 的映射符合预期。

### 2. P0：修复顺序路径 create_adapter 与 adapter.export 调用（Phase 1，止血）

- **位置**：`modules/apps/collection_center/executor_v2.py`，`_execute_with_python_components`。
- **修改**：去掉 `create_adapter` 的 `params=`、`download_dir=`，改为 `config=params`；**config 至少包含** `task`、`params`、`account`、`platform`；**download_dir** 统一约定：组件从 `config['task']['download_dir']` 读取（与现有 params 结构一致），不在 config 顶层重复，以便与 Phase 2 契约对齐。去掉 `adapter.export()` 的非法 `params=` 参数，仅调用 `adapter.export(page=page, data_domain=domain)`，域级参数通过 config 传入。并行路径同步改为使用 `create_adapter` + `adapter.login` / `adapter.export`，不再使用 `component_loader.load` + `_execute_component` / `_execute_export_component`；**若需并行模式支持子域循环**，则为 `execute_parallel_domains` 增加 `sub_domains` 参数并由路由传入，与顺序模式一致。确保顺序与并行为同一套组件执行模型。

### 3. P1：移除未使用的 db_session_maker（Phase 1）

- **位置**：`backend/routers/collection.py`。
- **修改**：调用 `_execute_collection_task_background` 时不再传入 `db_session_maker`；从 `_execute_collection_task_background` 的签名与 docstring 中删除该参数。后台任务继续使用 `AsyncSessionLocal()` 创建 session。

### 4. 采集架构简化：CollectionRunner + 脚本约定发现（Phase 2）

- **目标**：引入**薄调度层**（CollectionRunner）与**脚本即组件**的约定发现，顺序与并行为同一 runner 的两种调度模式；**不再以 PlatformAdapter / _export_map 为核心**，runner 按约定目录自动加载并调用脚本，方便重录、更新与测试。
- **组件契约**：
  - **登录**：返回类型约定为可判断成功/失败的结构（如 `{ success: bool, message?: str }` 或复用现有 `AdapterResult`），runner 据此决定是否继续导出及保存 storage_state。
  - **导出**：**`async def run(page, account, config) -> Result`**（或返回可序列化的导出结果）。推荐使用 `ExportResult` 等 dataclass，**不强制继承基类**；新录制脚本可仅实现一个 `run` 函数。
  - **config 结构**：为支持步骤可观测，config 中可包含 `step_callback`（及可选 `task_id` 等），脚本在 run 内部据此上报子步骤 details，与 add-collection-step-observability 一致；runner 在 run 前后仍做统一进度打点。
  - 兼容现有类组件：若模块暴露的是**类**且具有 `.run(page)` 或 `.run(page, account, config)` 方法，runner 实例化后调用，无需立刻重写所有脚本。
- **发现机制**：**约定目录 + 自动加载**。约定路径：`modules/platforms/{platform}/components/`，其中 **platform** 与目录名一一对应（若 API 的 platform_id 与目录名不同，由调用方在传入 runner 前完成映射）。`login.py` 为登录脚本；导出脚本为 `{domain}_export.py`（如 `orders_export.py`）。存在 **sub_domains** 时二选一约定：要么加载 `{domain}_{sub_domain}_export.py`（如 `orders_shop1_export.py`），要么仍加载 `{domain}_export.py` 并由 config 传入 `sub_domain`，脚本自行处理。**缺失脚本时**：若某 domain 在约定目录下无对应 `{domain}_export.py`（或带 sub 的变体），runner 将该域记入 failed_domains 并继续其余域，或在前置按平台/域做能力校验后仅执行有脚本的域；具体策略在实现时约定并文档化。
- **CollectionRunner（新建）**：
  - 新文件（约 300 行），从 executor_v2 中提取：browser/context 生命周期、进度回调、取消检测、弹窗处理、**文件处理**（见下）、结果汇总。
  - **文件处理范围**：runner 的「文件处理」仅指对本次采集得到的文件列表做整理/路径汇总并填入 `CollectionResult`，**不包含**写入 catalog 或触发数据同步；catalog/落盘仍由现有逻辑在 runner 返回后执行。
  - 核心流程：构建执行上下文（platform, account, config）→ 按约定加载 `login` 模块并执行登录 → **并行模式**下登录成功后保存 storage_state，各域导出时用该 storage_state 创建 context/page，与现有 executor 行为一致；顺序模式单 page 循环各域，并行模式多 context + `asyncio.gather`，**runner 接收 sub_domains 并在并行模式下与顺序模式一致地支持子域循环**（若 Phase 1 已为 execute_parallel_domains 增加 sub_domains 则行为对齐）。加载逻辑：若模块有 `run` 函数则直接调用；若为类则实例化后调用其 `run` 方法。**run() 抛异常时**：将该域记入 failed_domains 并继续其余域，是否对该域重试按 runner 层重试策略执行。
- **测试支持**：提供简单 **test harness**，例如 `python -m tools.test_script shopee orders_export`，自动启动 browser、构造 config、调用对应脚本的 `run`、输出结果，便于重录与回归验证。是否支持仅测登录（如 `shopee login`）可在实现时约定，本变更不强制。
- **路由**：`_execute_collection_task_background` 改为调用 `runner.run(task_id, platform, account, data_domains, ...)`，`parallel_mode` 作为参数传入，不再分两个入口。
- **废弃**：`PythonComponentAdapter` 从执行路径移除并标记废弃；采集执行路径不再依赖 `PlatformAdapter.get_export(domain)` 与 `_export_map`；`ComponentLoader` 从所有采集执行路径移除（retry_strategy 等仍可保留引用）；executor_v2 中旧 YAML 引擎标记废弃或删除，本变更内可不删除 executor_v2 文件本身，仅将路由切到 runner。

## Impact

### 受影响的规格

- **data-collection**：MODIFIED。Phase 1：顺序与并行统一使用同一套组件执行模型（PythonComponentAdapter）。Phase 2：采集执行统一通过 CollectionRunner + 约定目录脚本发现，组件契约为 `run(page, account, config)`（或类兼容），顺序/并行仅为调度策略差异；不再以 PlatformAdapter / _export_map 为核心。

### 受影响的代码与文档

| 类型 | 位置 | 修改内容 |
|------|------|----------|
| Phase 1 执行器 | modules/apps/collection_center/executor_v2.py | 修复 create_adapter(config=) 与 adapter.export(page, data_domain)；并行路径改为 create_adapter + adapter.login / adapter.export |
| Phase 2 调度层 | modules/apps/collection_center/collection_runner.py（新建） | 薄调度：browser 生命周期、进度/取消、弹窗、文件处理；按约定目录加载 login / {domain}_export 并调用 run(page, account, config) 或类.run |
| Phase 2 脚本加载 | modules/apps/collection_center/script_loader.py（新建，可选） | 约定目录发现：modules/platforms/{platform}/components/ 下 login.py、{domain}_export.py；支持函数 run 或类实例.run |
| Phase 2 测试工具 | tools/test_script.py（新建或扩展现有） | 入口如 python -m tools.test_script shopee orders_export：起 browser、构造 config、调脚本、报告结果 |
| Phase 2 执行器 | modules/apps/collection_center/executor_v2.py | 标记废弃或删除旧 YAML 引擎；路由切到 runner 后，本文件可保留作兼容或逐步删除 |
| Phase 2 适配层 | modules/apps/collection_center/python_component_adapter.py | 从执行路径移除并标记废弃；PlatformAdapter._export_map 不再作为采集入口 |
| 认证 | backend/routers/auth.py | get_current_user 失败时 raise HTTPException |
| 采集路由 | backend/routers/collection.py | 移除 db_session_maker；Phase 2 改为调用 runner.run(...) |
| 文档 | 可选 | 注明「采集架构：CollectionRunner + 约定目录脚本发现，组件契约为 run(page, account, config)，顺序/并行为同一 runner 的两种模式」 |

### 不修改

- 不修改数据同步、catalog、落盘逻辑；不在此变更中实现 API 采集或 hybrid 分流（属 add-hybrid-collection-api-playwright）。**Phase 2 runner 的文件处理**仅指对本次采集得到的文件列表做整理/路径汇总并填入 `CollectionResult`，不包含写入 catalog 或触发数据同步；catalog/落盘仍由现有逻辑在 runner 返回后执行。
- 不修改步骤可观测的 details 约定与前端展示。
- 不合并或替换 `backend/utils/auth.py` 中的另一套 `get_current_user`（本次仅修 `backend/routers/auth.py`）。**认证**：本变更仅修改 `backend/routers/auth.py` 的 `get_current_user`；`backend/main.py` 中若存在同名或类似依赖不在本变更范围内，需另案统一。

## Non-Goals

- 不改变「顺序单 page / 并行多 context」的并发与资源模型。
- 不在此变更中实现任务队列或 Celery 采集任务迁移；后台任务仍由 `asyncio.create_task` 启动。
- 不强制删除 executor_v2.py 或 component_loader 文件（Phase 2 可仅切换路由并标记废弃，后续单独清理）。
- 不强制从代码库删除 YAML 组件配置（若 retry_strategy 等仍使用 ComponentLoader 可保留）。
- Phase 2 不依赖 PlatformAdapter._export_map 作为组件入口；runner 自行按约定目录发现并调用脚本。
- **重试**：Phase 2 下采集重试由 runner 层负责（如对单次 run 失败重试）；若 retry_strategy 仍引用 ComponentLoader，仅保留与重试/兼容相关的按名加载，不与「约定目录发现」的主路径冲突。
- **取消**：不要求脚本内部支持细粒度取消；取消在每次 run 调用边界检测生效，单次 run 长时间不返回时用户取消会延迟生效，后续可单独优化。

## 与相关变更的关系

- **fix-local-collection-headed-mode**：解决本地有头可预期与文案；本变更 Phase 1 修复执行器与认证后，有头采集可正常跑通；Phase 2 的 runner 沿用同一套 browser 启动与 debug_mode 逻辑。
- **add-collection-step-observability**：步骤可观测与组件 async 契约已落地；Phase 1/2 均沿用同一套 status_callback 与 details 打点。
- **add-hybrid-collection-api-playwright**：API/Playwright 分流与 API 采集器；与本变更无冲突，可独立排期。
