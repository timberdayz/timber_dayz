# Tasks: 采集执行器修复与采集架构简化

**状态说明（2026-03-13）**：Phase 1 已完成；Phase 2 已作废（与当前组件版本管理设计冲突，见 DESIGN_ALIGNMENT_ASSESSMENT.md）。剩余 3.4 / 3.5 / 5.x 为可选验收或增强，不影响本变更闭环。

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

## Phase 2：架构简化（CollectionRunner + 脚本约定发现）— 已作废

**Phase 2 已取消实施**：与当前「组件版本管理 + 按 selected_version.file_path 加载 + PythonComponentAdapter」架构冲突，若实施会绕过版本表与 file_path。详见 `DESIGN_ALIGNMENT_ASSESSMENT.md`。以下任务仅保留作历史记录，不执行。

### 6. 约定目录与脚本加载 — 已取消

- ~~6.1 约定脚本路径~~（已取消：与版本按 file_path 加载冲突）
- ~~6.2 实现加载逻辑~~（已取消）
- ~~6.3 定义并文档化组件契约~~（已取消）
- ~~6.4 缺失脚本~~（已取消）

### 7. 新建 CollectionRunner — 已取消

- ~~7.1 新建 collection_runner.py~~（已取消）
- ~~7.2 核心流程~~（已取消）
- ~~7.3 保留步骤可观测与 CollectionResult~~（已取消）

### 8. 测试脚本入口 — 已取消

- ~~8.1 / 8.2 test harness~~（已取消）

### 9. 采集路由改为调用 runner — 已取消

- ~~9.1 / 9.2 路由切到 runner~~（已取消）

### 10. 废弃旧执行路径与适配层 — 已取消

- ~~10.1～10.3~~（已取消：当前设计保留 executor_v2 + 适配层 + 版本加载）

### 11. Phase 2 文档与验收 — 已取消

- ~~11.1 / 11.2~~（已取消）
