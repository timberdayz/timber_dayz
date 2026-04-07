# 数据采集能力 - 迁离 YAML 变更增量

## ADDED Requirements

### Requirement: 采集配置数据仅使用 Python 模块

系统 SHALL 将采集相关的配置数据（弹窗关闭选择器、执行顺序等）以 Python 模块形式提供，不再从 YAML 文件（如 popup_config.yaml、execution_order.yaml）读取，以便与「脚本层仅使用 .py」一致并统一维护。

#### Scenario: 弹窗选择器从 Python 模块获取

- **WHEN** 执行器或弹窗处理器需要某平台的关闭/遮罩选择器
- **THEN** 系统从该平台的 Python 配置模块（如 `modules/platforms/{platform}/popup_config.py` 或平台 config 模块）获取列表
- **AND** 系统不读取 `config/collection_components/{platform}/popup_config.yaml`
- **AND** 通用选择器可保留在代码内常量，平台特定选择器由 Python 模块导出

#### Scenario: 执行顺序从 Python 模块获取

- **WHEN** 执行器需要加载某平台的组件执行顺序（login → shop_switch → navigation → export 等）
- **THEN** 系统从 Python 模块（如 `modules/apps/collection_center/execution_order.py` 或平台级模块）获取 execution_sequence
- **AND** 系统不读取 `execution_order.yaml` 或 `default_execution_order.yaml` 文件
- **AND** 默认顺序可与现有硬编码逻辑一致，由 Python 模块统一导出

## MODIFIED Requirements

### Requirement: Python 组件统一执行

系统 SHALL 仅支持 Python 组件执行，不加载或解析 YAML 组件文件；组件加载器仅通过 `load_python_component()` 从 `modules/platforms/{platform}/components/*.py` 加载组件，测试工具仅扫描并测试 .py 组件，以避免双轨维护。

#### Scenario: 组件加载和执行

- **WHEN** executor_v2 需要加载组件
- **THEN** 系统使用 `component_loader.load_python_component()` 加载 Python 组件
- **AND** 系统不通过 `ComponentLoader.load()` 读取 `config/collection_components/**/*.yaml`
- **AND** 系统根据组件路径（如 `shopee/products_export`）解析平台和组件名
- **AND** 系统使用 `PythonComponentAdapter` 执行组件
- **AND** 系统返回统一格式的执行结果

#### Scenario: 组件路径解析

- **WHEN** 系统需要加载组件（如 `shopee/products_export`）
- **THEN** 系统解析路径获取平台（shopee）和组件名（products_export）
- **AND** 系统从 `modules/platforms/shopee/components/products_export.py` 加载组件类
- **AND** 系统创建组件实例并执行

#### Scenario: Python 组件元数据读取

- **WHEN** 系统加载 Python 组件类
- **THEN** 系统通过 `inspect` 模块读取类属性（platform、component_type、data_domain）
- **AND** 系统验证元数据完整性（必需字段存在）
- **AND** 系统使用元数据选择正确的组件实例

#### Scenario: 测试工具仅支持 Python 组件

- **WHEN** 用户或前端通过测试工具（如 tools/test_component.py、run_component_test.py）测试组件
- **THEN** 系统仅扫描并加载 `modules/platforms/{platform}/components/*.py`
- **AND** 系统不加载或执行基于 YAML 的组件
- **AND** 组件版本表中的 file_path 为 .py 时才参与加载与测试
