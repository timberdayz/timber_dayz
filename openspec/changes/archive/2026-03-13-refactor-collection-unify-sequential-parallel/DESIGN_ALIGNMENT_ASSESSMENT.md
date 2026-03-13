# refactor-collection-unify-sequential-parallel 与最新采集模块设计对齐评估

**评估时间**：2026-03-13  
**提案首次提交**：2026-02-25（git commit: feat：采集执行器架构简化）

---

## 一、提案创建时间

- **Git 首次引入**：`openspec/changes/refactor-collection-unify-sequential-parallel/proposal.md` 于 **2026-02-25** 随提交「feat：采集执行器架构简化」加入。
- 该提案早于后续已落地的 **optimize-component-version-management**（组件唯一性、按 file_path 加载、版本管理、测试与生产一致等），且 Phase 2 未考虑「组件版本管理」与「按版本选 file_path」的当前设计。

---

## 二、Phase 1 与当前设计的一致性

| 内容 | 提案 Phase 1 | 当前实现与主 spec | 结论 |
|------|--------------|-------------------|------|
| 认证 | get_current_user 失败时 raise HTTPException(401/403) | 已实现 | 一致 |
| 顺序路径 | create_adapter(config=params)，adapter.export(page, data_domain)，download_dir 从 config['task']['download_dir'] 读取 | 已实现 | 一致 |
| 并行路径 | 与顺序路径同一套 create_adapter + adapter.login / adapter.export，不再用 component_loader.load + _execute_component | 已实现 | 一致 |
| db_session_maker | 从 _execute_collection_task_background 移除 | 已移除 | 一致 |

**结论**：Phase 1 已全部完成，且与当前采集模块设计一致；顺序/并行双轨已统一为同一套组件执行模型（PythonComponentAdapter + Python 组件）。

---

## 三、Phase 2 与最新采集模块设计的冲突与偏差

当前采集模块的**既定设计**（来自 data-collection spec、optimize-component-version-management 及已实现代码）：

1. **组件版本管理**：ComponentVersion 表、component_name 标准化、版本化 file_path（如 `login_v1_0_1.py`）、稳定版/测试版/A/B。
2. **生产按版本加载**：执行器通过 **ComponentVersionService.select_version_for_use()** 得到 **selected_version**，再按 **selected_version.file_path** 调用 **load_python_component_from_path()** 加载组件类，保证「生产跑稳定版、测试跑选中版本」。
3. **执行路径**：仍经 **PythonComponentAdapter** 执行；当 component dict 含有 **\_python_component_class**（由 file_path 加载）时，直接使用该类，不再按 comp_name 加载；适配层负责账号解密、平台映射、子组件调用等。
4. **约定目录**：脚本仍在 `modules/platforms/{platform}/components/`，但**具体用哪个文件**由版本表与 file_path 决定，而非「约定文件名」如固定 `login.py`、`orders_export.py`。

Phase 2 提案中的设计：

- 引入 **CollectionRunner**，按**约定目录 + 约定文件名**发现脚本：`login.py`、`{domain}_export.py`，无版本表参与。
- **废弃 PythonComponentAdapter**，采集执行不再经适配层；runner 直接加载脚本并调用 `run(page, account, config)` 或类 `.run()`。
- 未提及 ComponentVersionService、selected_version、file_path、多版本、稳定版选择。

因此存在以下**不一致**：

| 维度 | 当前采集模块设计（主 spec + 已实现） | 本提案 Phase 2 | 冲突/偏差 |
|------|--------------------------------------|----------------|-----------|
| 组件来源 | 由 **ComponentVersionService** 选版，按 **selected_version.file_path** 加载（版本化文件名如 login_v1_0_1.py） | 按**约定路径**加载 login.py、{domain}_export.py，无版本选择 | **冲突**：Phase 2 会绕过版本管理，无法实现「多版本、稳定版、按 file_path 执行」 |
| 适配层 | **PythonComponentAdapter** 仍为执行入口；component dict 可带 _python_component_class（来自 file_path） | 从执行路径移除并废弃 PythonComponentAdapter | **冲突**：当前测试与生产都依赖适配层 + 注入类/file_path 加载类 |
| 加载方式 | **load_python_component_from_path(file_path)** + 版本表 file_path | 新建 script_loader / runner 内按目录约定加载 | **冲突**：与「按 DB 中 file_path 加载」的设计不符 |
| 文件名约定 | 版本化文件名（如 login_v1_0_1.py）、fallback 主文件（login.py） | 固定 login.py、{domain}_export.py | **偏差**：无法表达多版本并存 |

---

## 四、结论与建议

1. **Phase 1**  
   - 已实施完毕，且与当前设计一致，可视为**已闭环**。  
   - 未完成的 3.4（并行 sub_domains）、3.5/5.x（验收）为增强与验收，不改变架构。

2. **Phase 2（CollectionRunner + 约定发现）**  
   - **与最新采集模块设计不符**：若按原样实施，会与「组件版本管理 + 按 selected_version.file_path 加载 + PythonComponentAdapter 执行」的既定架构冲突。  
   - 若仍希望引入「薄调度层」或统一 runner 抽象，建议在**保留版本管理**的前提下重设计 Phase 2，例如：  
     - Runner 只负责：流程编排、browser/context 生命周期、进度/取消、弹窗、文件汇总；  
     - **组件加载**仍由现有链路负责：ComponentVersionService 选版 → load_python_component_from_path(selected_version.file_path) → 将得到的类交给适配层或统一执行接口执行；  
     - 不在 Phase 2 中废弃 PythonComponentAdapter，除非另有替代方案且能兼容版本管理与测试注入。

3. **建议**  
   - 将本提案的 **Phase 2 视为过期设计**，不作为当前实现依据。  
   - 若后续做「采集执行层重构」，应基于现有 **executor_v2 + ComponentVersionService + file_path + 适配层** 的模型做演进（例如抽出薄 runner 但保留版本加载与适配层），并同步更新本提案的 Phase 2 说明或新增 delta spec，使之与主 spec 中的组件版本管理、file_path 加载、适配层角色一致。
