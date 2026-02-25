# Tasks: 采集执行器修复与采集架构简化

## Phase 1：止血（P0/P1 + 双轨统一）— 已完成

### 1. P0：认证依赖改为抛出 HTTPException

- [x] 1.1 在 `backend/routers/auth.py` 的 `get_current_user` 中，将所有 `return error_response(..., status_code=401)` 或 `return error_response(..., status_code=403)` 改为 `raise HTTPException(status_code=401 或 403, detail="...")`。
- [x] 1.2 确认 `backend/main.py` 中已注册的 `HTTPException` exception_handler 对 401/403 的映射与 `error_response` 格式一致；无需新增 handler，验证即可。

### 2. P0：修复顺序路径 create_adapter 与 adapter.export 调用

- [x] 2.1 在 `executor_v2.py` 的 `_execute_with_python_components` 中，将 `create_adapter(..., params=..., download_dir=...)` 改为 `create_adapter(platform=..., account=..., config=params, ...)`，去掉 `params=` 与 `download_dir=`；此处传入的 **config 即当前 params 对象**（同一结构），确保该对象含 `task`、`params`、`account`、`platform` 等与现有结构一致。
- [x] 2.2 确认该 config（即原 params）至少包含 `task`、`params`、`account`、`platform`；**download_dir** 统一从 `config['task']['download_dir']` 读取，不与顶层键重复。组件从 `self.config` 可正确读取日期范围、粒度等；若有缺失则补全 config 结构并与 Phase 2 config 契约对齐。
- [x] 2.3 修复同一函数内对 `adapter.export()` 的调用：去掉不存在的 `params=` 参数，仅调用 `adapter.export(page=page, data_domain=domain)`；域级参数通过 config 传入（若需每域不同 config，可每域用含该域 params 的 config 新建 adapter）。

### 3. P0：并行路径统一为同一套组件执行模型

- [x] 3.1 **并行路径登录**：在 `execute_parallel_domains` 的登录阶段，不再使用 `component_loader.load(f"{platform}/login", ...)` 与 `_execute_component`。改为：构造与顺序路径一致的 `params`，调用 `create_adapter(platform=..., account=..., config=params, ...)`，在 `login_page` 上调用 `_execute_python_component(login_page, adapter, "login", params)` 或 `adapter.login(login_page)`；保留提取 `storage_state`、成对打点与异常处理。
- [x] 3.2 **并行路径单域导出**：在 `_execute_single_domain_parallel` 中，不再使用 `component_loader.load` 与 `_execute_export_component`。改为：为每个域用含该域参数的 config 创建 adapter，调用 `adapter.export(page=domain_page, data_domain=data_domain)`；保留 `storage_state`、独立 context、成对打点与返回值 `(file_path, success)`。
- [x] 3.3 从并行路径移除对 `_execute_component` / `_execute_export_component` 的依赖；`component_loader` 仍被 `retry_strategy.py` 等使用，仅从并行执行路径移除对 load(login/export) 的调用。
- [ ] 3.4 **若需并行模式支持子域**：为 `execute_parallel_domains` 增加参数 `sub_domains`，在 `backend/routers/collection.py` 调用时传入 `sub_domains=sub_domains`，与顺序模式一致。（当前仅顺序模式支持 sub_domains。）
- [ ] 3.5 验证：顺序与并行两种模式执行相同数据域，步骤时间线语义一致，无 create_adapter 参数错误。（需人工验收。）

### 4. P1：移除未使用的 db_session_maker

- [x] 4.1 在 `backend/routers/collection.py` 中，删除调用 `_execute_collection_task_background` 时传入的 `db_session_maker=db.get_bind()` 参数。
- [x] 4.2 在 `_execute_collection_task_background` 的函数签名与 docstring 中删除 `db_session_maker` 参数及其说明。

### 5. Phase 1 验收

- [ ] 5.1 执行一次顺序采集与一次并行采集，确认任务可正常完成且步骤日志完整。（需人工验收。）
- [ ] 5.2 确认 `/api/notifications/unread-count` 在未认证时返回 401 而非 500。
- [ ] 5.3 （推荐）为 `get_current_user` 的 HTTPException 行为及 create_adapter/export 调用添加单元测试或回归测试。

---

## Phase 2：架构简化（CollectionRunner + 脚本约定发现）— 未实施

（当前路由仍调用 `CollectionExecutorV2.execute` / `execute_parallel_domains`，未引入 CollectionRunner。）

### 6. 约定目录与脚本加载

- [ ] 6.1 约定脚本路径：`modules/platforms/{platform}/components/` 下 `login.py` 为登录脚本，`{domain}_export.py`（如 `orders_export.py`）为按域导出脚本；**platform** 与目录名一一对应，若存在 platform_id→目录名映射由调用方在调用 runner 前完成。**sub_domains** 存在时约定二选一：加载 `{domain}_{sub_domain}_export.py` 或仍加载 `{domain}_export.py` 并由 config 传入 `sub_domain`，与 runner 参数 sub_domains 一致。runner 按 platform、domain、可选 sub_domain 动态解析模块路径并加载。
- [ ] 6.2 实现加载逻辑（可在 `collection_runner.py` 内或独立 `script_loader.py`）：加载模块后，若存在 `run` 函数则视为可调用 `run(page, account, config)`；若模块暴露的是类且具有 `run` 方法，则实例化（传入 account/config 或 ctx）后调用其 `run(page)` 或 `run(page, account, config)`，以兼容现有类组件。
- [ ] 6.3 定义并文档化组件契约：登录返回可判断成功/失败的结构（如 `{ success: bool, message?: str }` 或 AdapterResult）；导出推荐 `async def run(page, account, config) -> ExportResult`（或等价类型），不强制继承基类。**config** 包含 `step_callback`（及可选 `task_id`）以便脚本上报子步骤，与步骤可观测一致。
- [ ] 6.4 **缺失脚本**：当某 domain（或 domain+sub_domain）在约定目录下无对应导出脚本时，将该域记入 failed_domains 并继续其余域；或在前置按平台/域做能力校验，仅对存在脚本的域执行。**sub_domains 脚本约定**：在实现时在两种方式（`{domain}_{sub_domain}_export.py` 或 `{domain}_export.py` + config 传入 sub_domain）中选定一种作为项目约定并文档化。策略在实现时确定并文档化。

### 7. 新建 CollectionRunner

- [ ] 7.1 新建 `modules/apps/collection_center/collection_runner.py`，实现薄调度层：browser/context 生命周期、进度回调、取消检测、弹窗处理、文件处理、结果汇总（可从 executor_v2 提取并精简）。
- [ ] 7.2 核心流程：构建执行上下文（platform, account, config）→ 按约定加载并执行 login 脚本 → 按域加载并执行 `{domain}_export` 脚本；**并行模式**下登录成功后保存 storage_state，各域导出时用该 storage_state 创建 context/page；顺序模式单 page 循环各域，并行模式多 context + `asyncio.gather`，组件调用代码复用。**run() 抛异常时**将该域记入 failed_domains 并继续其余域，是否重试按 runner 层策略。**不依赖** PlatformAdapter.get_export(domain) 或 _export_map。
- [ ] 7.3 保留与现有一致的 `_update_status`、步骤可观测打点、`CollectionResult` 结构及文件处理逻辑；整任务失败（如登录失败）时 runner 设置 `CollectionResult.error_message` 以便路由写回 `task.error_message`。文件处理仅指对本次采集得到的文件列表做整理/路径汇总并填入 `CollectionResult`，不包含写入 catalog 或触发数据同步。

### 8. 测试脚本入口（test harness）

- [ ] 8.1 提供简单入口，例如 `python -m tools.test_script shopee orders_export`：自动启动 browser（可配置有头/无头）、构造最小 config（account、platform、date_range 等）、加载并调用对应脚本的 `run(page, account, config)`（或类实例.run），输出结果或错误，便于重录与回归验证。
- [ ] 8.2 支持指定 platform 与 domain（或脚本名如 `orders_export`），可选参数如 `--headed`、`--account-id`；是否支持仅测登录（如 `shopee login`）在实现时约定，本变更不强制。与现有 `tools/test_component.py` 可共存，后续逐步迁移调用方到 test_script。

### 9. 采集路由改为调用 runner

- [ ] 9.1 在 `backend/routers/collection.py` 的 `_execute_collection_task_background` 中，改为实例化并调用 `CollectionRunner.run(task_id, platform, account, data_domains, date_range, granularity, debug_mode, parallel_mode, max_parallel, ...)`，不再根据 parallel_mode 分支调用 `executor.execute` 或 `executor.execute_parallel_domains`。
- [ ] 9.2 确保 runner 接收与现有一致的参数（含 sub_domains）；并行模式下与顺序模式一致支持子域循环（若 Phase 1 已为 execute_parallel_domains 增加 sub_domains 则实现对齐），并返回 `CollectionResult`。

### 10. 废弃旧执行路径与适配层

- [ ] 10.1 在 `executor_v2.py` 中标记废弃：旧 YAML 引擎（`_execute_component`、`_execute_step`、`_execute_export_component`、`_execute_discovery_component`、`_load_component_with_version` 等）添加弃用说明或移至单独模块；或本变更内仅切换路由，不删除 executor_v2 文件。
- [ ] 10.2 在 `python_component_adapter.py` 顶部添加弃用说明：采集执行已迁移至 CollectionRunner + 约定目录脚本发现，本模块仅保留供兼容或非采集场景。Phase 2 不再以 PlatformAdapter._export_map 为采集入口。
- [ ] 10.3 确认并处理以下已知调用方对 executor / PythonComponentAdapter 的依赖：`tools/test_component.py`、`tools/record_component.py`、`tests/test_executor_v2.py` 等。可改为使用 runner 或 `tools.test_script`，或保留最小兼容封装使旧测试/工具仍能运行。

### 11. Phase 2 文档与验收

- [ ] 11.1 在 `collection_runner.py` 或 data-collection 文档中注明：采集架构为 CollectionRunner（薄调度）+ 约定目录脚本发现，组件契约为 `run(page, account, config)`（或类兼容），顺序与并行为同一 runner 的两种调度模式。
- [ ] 11.2 执行顺序与并行采集各一次，确认与 Phase 1 行为一致且无回归；确认路由仅依赖 runner，不再直接调用 executor 的 execute/execute_parallel_domains；确认 runner 不依赖 PlatformAdapter.get_export / _export_map。
