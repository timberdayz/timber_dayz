# Canonical 采集组件规则

本文档定义 V2 架构下哪些文件才算正式逻辑组件入口，哪些文件只能视为历史兼容层或归档参考。

配套清单见：

- [ACTIVE_COLLECTION_COMPONENTS.md](F:\Vscode\python_programme\AI_code\xihong_erp\docs\guides\ACTIVE_COLLECTION_COMPONENTS.md)

## 核心原则

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

这类文件是 runtime artifact，不是主维护入口：

- `login_v1_0_3.py`
- `orders_export_v1_0_0.py`

### 配置文件

这类文件只承载选择器、文案、候选项，不是逻辑组件：

- `*_config.py`
- `config_registry.py`

### 辅助文件

这类文件是 helper，不是逻辑组件：

- `overlay_guard.py`
- 其他仅提供工具函数或常量的文件

### 录制/兼容层文件

这类文件属于历史迁移资产，不再作为默认主入口：

- `miaoshou_login.py`
- `recorder_*`
- `*_recorder.py`
- `*_test_*.py`

## 与活跃组件清单的关系

一个文件满足 canonical 命名规则，只代表它**有资格**成为正式入口；
是否真的进入默认运行链路，还要看它是否在活跃组件清单里。

也就是说：

- canonical 解决“命名和结构是否合规”
- active list 解决“当前是否真的还在主链路中”

## 默认维护规则

默认情况下：

- 只编辑 `modules/platforms/<platform>/components/` 下的 canonical 文件
- 不默认编辑版本化文件
- 不默认编辑 recorder-era 中间文件
- 不默认编辑 archive 文件

## 一句话规则

如果一个文件既不符合固定槽位命名，也不是 `*_export.py`，它默认就不应该再被当成新的正式采集组件入口。
