# Change: 采集模块彻底迁离 YAML（组件与配置统一 Python）

## Why

1. **单一脚本格式已落地**：采集脚本已统一为 `modules/platforms/{platform}/components/*.py`，录制器主产出为 Python，执行器主路径通过 Python 适配器加载 .py。但代码中仍保留 YAML 组件加载（`ComponentLoader.load` / `_load_from_file`）、YAML 配置（`popup_config.yaml`、`execution_order.yaml` / `default_execution_order.yaml`）以及 `tools/test_component.py` 对 YAML 组件的依赖，造成双轨维护与认知负担。
2. **规范与实现一致**：`.cursorrules` 与《采集脚本编写规范》明确「采集脚本必须用 .py，不允许 YAML」。配置类数据（弹窗选择器、执行顺序）若继续放在 YAML，与「脚本层只认 .py」不一致；迁到 Python 数据模块可统一维护、类型友好、便于测试。
3. **可维护性**：移除历史 YAML 路径后，新贡献者只需理解 Python 组件与 Python 配置模块，无需再区分 YAML 与 .py 两套入口。

## What Changes

- **ComponentLoader**：废弃或移除基于文件的 YAML 加载（`load()` 中走 `_load_from_file` 读 `config/collection_components/**/*.yaml`）。执行器与测试工具仅通过 `load_python_component()` 或等价 Python 加载路径获取组件；若仍需「按路径解析并返回配置字典」的兼容层，可改为从 Python 组件类元数据生成字典，而非读 YAML 文件。迁移完成后，若执行器等调用方已全部改为 `load_python_component()`，则可以将 `load()` 标记为废弃或仅保留极薄的兼容层。
- **弹窗配置**：`popup_config.yaml`（`config/collection_components/{platform}/popup_config.yaml`）迁到 Python 数据模块（如 `modules/platforms/{platform}/popup_config.py` 或集中模块），由 `UniversalPopupHandler` 通过 import 获取 `get_close_selectors(platform)` 等，不再读取 YAML 文件。
- **执行顺序配置**：`execution_order.yaml` / `default_execution_order.yaml` 迁到 Python 数据模块（如 `modules/apps/collection_center/execution_order.py` 或按平台在 `modules/platforms/{platform}/execution_order.py`），由 executor_v2 的 `_load_execution_order()` 改为从该模块读取，不再读 YAML 文件。
- **录制器保存接口**：`/recorder/save` 仅支持保存 Python 组件（请求体仅接受 `python_code`，不再接受 `yaml_content`）；若仅传 `yaml_content` 则返回 4xx 并提示仅支持 Python 保存。保存目标为 `modules/platforms/{platform}/components/{component_name}.py`，移除 YAML 保存分支，并确保 `ComponentVersion.file_path` 只记录 .py 路径。前端录制器保存仅提交 `python_code`，不依赖 `yaml_content`。
- **tools/test_component.py**：仅支持加载与测试 Python 组件（.py）；移除对 YAML 组件的扫描、加载与执行分支。若存在 `tools/run_component_test.py` 的 YAML 分支，一并改为仅支持 .py（与当前录制器测试链路一致）。
- **版本服务与数据迁移**：使用现有迁移脚本（如 `scripts/migrate_component_versions_to_python.py`）或等价逻辑，将 `component_versions.file_path` 中残留的 `.yaml` 路径迁移为 `.py`；executor_v2 中基于 `file_path.replace('.yaml', '')` 的兼容逻辑在迁移完成后移除，仅在 `file_path` 为 .py 时参与加载和测试。
- **其他引用**：所有仍引用 `config/collection_components/**/*.yaml` 或 `ComponentLoader.load()` 用于「组件内容」的调用点（如 retry_strategy、executor_v2 的 component_call、版本服务返回的 file_path 为 .yaml 的路径）改为使用 Python 组件路径或从 Python 组件类获取元数据；必要时保留「file_path 为 .py」的版本服务行为并在文档中明确仅支持 .py。
- **文档与测试**：更新《采集脚本编写规范》或 RECORDER_PYTHON_OUTPUT 中关于 popup_config、执行顺序的说明；单元测试与 E2E 测试中移除对 YAML 组件或 YAML 配置文件的依赖，改为使用 Python 模块或 fixture（包括 `tests/test_component_loader.py`、`tests/test_executor_v2.py`、tests/e2e 下对 popup_config.yaml 与 YAML 组件的断言）。

**BREAKING**：任何仍依赖「从 config/collection_components 目录读取 .yaml 组件或 popup_config.yaml / execution_order.yaml」的脚本或配置将失效，需改为使用 Python 模块。

## Impact

- **Affected specs**: data-collection
- **Affected code**:
  - `modules/apps/collection_center/component_loader.py`（load / _load_from_file / load_all / get_component_info 等与 YAML 相关的逻辑）
  - `modules/apps/collection_center/executor_v2.py`（_load_component、_load_execution_order、基于 file_path 的版本加载与 `.yaml` → `.py` 迁移后的仅 .py 加载逻辑）
  - `modules/apps/collection_center/popup_handler.py`（_load_platform_config 从 YAML 改为从 Python 模块读取）
  - `modules/apps/collection_center/retry_strategy.py`（若通过 component_loader.load 加载组件）
  - `backend/routers/component_recorder.py`（/recorder/save 仅保存 .py，不再写入 YAML 组件文件）
  - `tools/test_component.py`（YAML 扫描与加载分支）
  - `tools/run_component_test.py`（若有 YAML 分支则移除）
  - 新建：`modules/platforms/{platform}/popup_config.py` 或等价；`modules/apps/collection_center/execution_order.py` 或按平台
  - 脚本：`scripts/cleanup_yaml_components.py`、`scripts/migrate_component_versions_to_python.py`（在本变更中作为一次性迁移/清理工具使用）
  - **ComponentLoader.components_dir**：迁移后该属性仅用于兼容或测试；生产侧的组件加载与列表均以 `modules/platforms` 下的 .py 为准，不再依赖该目录下的 YAML。
- **Tests**: `tests/test_component_loader.py`、`tests/test_executor_v2.py`、tests/e2e/test_shopee_collection.py、test_complete_collection_to_sync.py 等中涉及 popup_config.yaml 或 YAML 组件的断言需改为 Python 数据或 .py 组件。

## Migration / Rollback

- **Migration**：在切换到仅 Python 组件与配置之前，先提供对应的 Python 配置模块（popup_config、execution_order 等），并执行 component_versions.file_path 的 `.yaml` → `.py` 迁移（如通过 `scripts/migrate_component_versions_to_python.py`）。完成迁移与代码切换后，`config/collection_components` 下残留的 YAML 文件可通过 `scripts/cleanup_yaml_components.py` 备份并清理。
- **Rollback**：本变更不保留「切回 YAML 执行路径」的运行时开关，回滚需通过 Git 或部署层回退到变更前版本（包含 YAML 加载逻辑与 YAML 配置）。

## Non-Goals

- 不改变采集脚本的运行时契约（仍是 async def run(page, account, config) 与 ResultBase）；仅改变「组件与配置的载体」从 YAML 到 Python。
- 不在此变更中实现新的业务功能；仅做载体迁移与旧路径清理。
