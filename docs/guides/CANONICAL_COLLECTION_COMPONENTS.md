# Canonical 采集组件规则

本文档定义 V2 架构下哪些文件才算“正式逻辑组件入口”，哪些文件只能视为历史兼容层或辅助文件。

## 目标

V2 的核心原则是：

- 一个逻辑组件只保留一个 canonical 源文件
- 正式测试、批量注册、后续迁移都围绕 canonical 文件展开
- 兼容文件、录制草稿、配置文件不能再冒充正式组件入口

## Canonical 文件命名

### 固定槽位

以下文件名天然属于 canonical 组件入口：

- `login.py`
- `navigation.py`
- `date_picker.py`
- `shop_switch.py`
- `filters.py`

对应逻辑组件名格式：

- `platform/login`
- `platform/navigation`
- `platform/date_picker`
- `platform/shop_switch`
- `platform/filters`

### 数据域导出槽位

任意 `*_export.py` 都属于 canonical 导出组件入口，例如：

- `orders_export.py`
- `products_export.py`
- `analytics_export.py`
- `finance_export.py`
- `services_export.py`
- `services_agent_export.py`

对应逻辑组件名格式：

- `platform/orders_export`
- `platform/products_export`
- `platform/services_agent_export`

## 非 Canonical 文件

以下文件不应作为默认维护目标，也不应进入默认批量注册主链路。

### 版本化运行时文件

这类文件是运行时产物，不是主维护入口：

- `login_v1_0_3.py`
- `orders_export_v1_0_0.py`

### 配置文件

这类文件只承载选择器、文案、候选项，不是逻辑组件：

- `*_config.py`
- `config_registry.py`

### 辅助/守卫文件

这类文件是 helper，不是逻辑组件：

- `overlay_guard.py`
- 其他仅提供工具函数或常量的文件

### 录制/兼容层文件

这类文件属于历史迁移资产，不再作为默认主入口：

- `miaoshou_login.py`
- `recorder_*`
- `*_recorder.py`
- `*_test_*.py`

## V2 默认维护原则

后续新开发或重构时，默认只编辑：

- `modules/platforms/<platform>/components/` 下的 canonical 文件

不应默认编辑：

- 版本化文件
- 录制生成中间文件
- 兼容包装层
- 配置文件之外的历史辅助层

## 与版本管理的关系

V2 下应区分两层：

1. canonical 源文件  
用于日常开发、重构、代码审查

2. stable/versioned 运行时文件  
用于组件版本管理、正式运行、回滚

这意味着：

- 开发源头看 canonical
- 运行入口看 stable `file_path`
- 不再长期保留第三层“兼容主实现文件”作为默认维护对象

## 当前迁移策略

V2 第一阶段不会立即删除历史文件，但会逐步收敛为：

- 批量注册优先识别 canonical 规则
- 文档与 UI 默认展示 canonical 组件语义
- 历史兼容文件保留在磁盘上，但退出默认维护主路径

## 一句话规则

如果一个文件不是固定槽位文件，且也不是 `*_export.py`，那它默认就不应该被当成新的正式采集组件入口。
