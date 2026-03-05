# Tasks: 采集模块彻底迁离 YAML

**目标**：组件加载、弹窗配置、执行顺序、测试工具均不再依赖 YAML 文件，统一使用 Python 模块或 Python 组件。

**实施顺序建议**：为避免执行器在过渡期既拿不到 YAML 又拿不到 Python 的兼容字典而断链，建议按 **1 → 3.1/3.2 → 2 → 4 → 5 → 6** 执行：先迁配置与执行顺序/弹窗（1），再让执行器与重试逻辑统一走 `load_python_component()`（3），再收口 ComponentLoader 的 YAML（2），最后改测试工具与清理（4、5、6）。

## 1. 执行顺序与弹窗配置迁到 Python

- [x] 1.1 新增 Python 数据模块：默认执行顺序（如 `modules/apps/collection_center/execution_order.py`）导出 `get_default_execution_order()` 与按平台可选的 `get_execution_order(platform)`，返回与当前 YAML 中 `execution_sequence` 相同结构；若无现有 YAML 文件则使用与 executor_v2 中 `_get_default_execution_order()` 一致的硬编码列表。
- [x] 1.2 新增或扩展平台级 Python 配置：每平台弹窗选择器迁到 Python（如 `modules/platforms/shopee/popup_config.py` 或统一在 `modules/platforms/{platform}/config.py` 中），导出 `get_close_selectors()`、`get_overlay_selectors()` 等，与当前 popup_config.yaml 结构等价。
- [x] 1.3 修改 `executor_v2._load_execution_order()`：改为从上述 Python 模块读取，不再读取 `execution_order.yaml` / `default_execution_order.yaml`。
- [x] 1.4 修改 `UniversalPopupHandler._load_platform_config()`：改为从上述平台 Python 配置模块读取，不再读取 `popup_config.yaml`；保留通用选择器列表在代码内常量。

## 2. ComponentLoader 仅支持 Python 组件

- [x] 2.1 将 `ComponentLoader.load()` 的语义改为「仅支持 Python 组件」：按 component_path 解析 platform/component_name，调用 `load_python_component()` 获取类，再从类元数据（或约定接口）生成兼容旧调用方的字典形态；或废弃 `load()`，所有调用方改为使用 `load_python_component()` 并适配调用方。若采用废弃，则 `load()` 标记 DeprecationWarning 并内部转发到 Python 加载路径。
- [x] 2.2 移除 `_load_from_file()` 中对 YAML 文件的读取；移除 `load_all()` 中 `*.yaml` 扫描，改为扫描 `modules/platforms/*/components/*.py` 并仅通过 `load_python_component()` 注册/列表。迁移后 `ComponentLoader.components_dir` 仅用于兼容或测试，生产加载与列表以 `modules/platforms` 下 .py 为准。
- [x] 2.3 `get_component_info(component_path)` 改为基于 Python 组件类元数据返回（name、platform、type、data_domain 等），不再调用 `load()` 读 YAML。
- [x] 2.4 更新 executor_v2 中所有 `component_loader.load(...)` 调用：若当前依赖返回的字典结构，改为从 Python 组件类实例或元数据构建等价结构；配合 component_versions.file_path 迁移，移除对 `.yaml` 的兼容逻辑（如 `replace('.yaml', '')`），统一按 .py 路径处理。

## 3. 执行器与重试逻辑统一走 Python

- [x] 3.1 executor_v2 中 `_load_component()`（及版本选择后加载）、component_call 子组件加载，统一改为 `load_python_component()` + 执行 Python 组件，不再传入 YAML 字典给执行引擎。
- [x] 3.2 `retry_strategy.py` 中若存在 `component_loader.load(...)`，改为使用 `load_python_component()` 或从执行上下文获取已加载的 Python 组件类，避免读 YAML。

## 4. 测试工具仅支持 .py

- [x] 4.1 `tools/test_component.py`：列出组件时仅扫描 `modules/platforms/{platform}/components/*.py`，不再扫描 `*.yaml`；加载组件时仅使用 `load_python_component()` 或等价 Python 加载，移除 YAML 分支。
- [x] 4.2 `tools/run_component_test.py`：若存在按 YAML 组件路径执行的分支，移除或改为仅支持 .py 路径（与当前录制器测试一致）。
- [x] 4.3 其他脚本（如 `tools/record_component.py`、`tools/demo_component_loader.py`）中仍引用 `component_loader.load(...)` 或 YAML 输出的，改为 Python 组件或标注废弃/仅演示用。
- [x] 4.4 `backend/routers/component_recorder.py`：移除 `/recorder/save` 中 YAML 保存分支；请求体仅以 `python_code` 为有效输入，不再接受 `yaml_content`，若仅传 `yaml_content` 则返回 4xx 并提示仅支持 Python 保存。保存目标为 `modules/platforms/{platform}/components/{component_name}.py`，`ComponentVersion.file_path` 仅记录 .py 路径。

## 5. 清理与文档

- [x] 5.1 删除或归档 `config/collection_components/**/*.yaml` 中仍存在的组件/配置 YAML 文件（若仓库中已无则跳过）；从文档中移除「YAML 组件」「popup_config.yaml」「execution_order.yaml」作为推荐配置方式的描述。
- [x] 5.2 更新 `docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md` 或 `docs/guides/RECORDER_PYTHON_OUTPUT.md`：弹窗配置、执行顺序改为引用 Python 模块路径与导出约定。
- [x] 5.3 单元/ E2E 测试：移除对 `popup_config.yaml`、YAML 组件的存在性或内容的依赖；改为使用 Python 模块或 fixture 提供弹窗配置与执行顺序；更新 `tests/test_component_loader.py`、`tests/test_executor_v2.py`、test_shopee_collection、test_complete_collection_to_sync 等中相关断言。
- [x] 5.4 脚本与迁移：梳理并更新 `scripts/cleanup_yaml_components.py`、`scripts/migrate_component_versions_to_python.py` 的使用说明，将其标记为「YAML → Python 迁移」的一次性脚本（或在变更完成后归档），并在文档中简要说明推荐的迁移顺序。
- [x] 5.5 在代码切换前/后执行 `scripts/migrate_component_versions_to_python.py`（或等价逻辑），将存量 `component_versions.file_path` 从 .yaml 迁为 .py；或在部署文档中明确该步骤为必须，便于验收与上线不遗漏。

## 6. 验收

- [x] 6.1 主采集流程（登录 → 导航 → 导出）仅通过 Python 组件与 Python 配置运行，不读取任何 `config/collection_components` 下 YAML。
- [x] 6.2 前端「测试组件」与 CLI `tools/run_component_test.py` 仅使用 .py 组件，通过。
- [x] 6.3 `openspec validate migrate-collection-off-yaml --strict` 通过。

**验收命令**（无需全局安装，使用 npx）：  
`npx --yes @fission-ai/openspec@latest validate migrate-collection-off-yaml --strict`
