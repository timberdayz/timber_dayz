# Canonical 采集组件清单

本文档用于定义当前项目中**每个平台、每个逻辑槽位**应保留的唯一 canonical 组件入口，并标注其当前成熟度，避免用户在多个重复组件、测试件或历史别名之间猜测该改哪一个。

## 评估标准

- **成熟**：已包含真实业务流程、复杂交互处理、下载/状态/异常兜底，可直接作为 canonical 迁移基础
- **可用**：已具备主流程，但仍偏薄或存在已知规则欠账，需要后续继续优化
- **排除**：不应作为用户默认维护对象，包括测试件、基类壳子、历史别名、配置文件

## Shopee

### Canonical 槽位

| 槽位 | 当前基础文件 | 成熟度 | 说明 |
|------|--------------|--------|------|
| `shopee/login` | `modules/platforms/shopee/components/login.py` | 可用 | 统一委托 `LoginService`，是当前正确入口 |
| `shopee/navigation` | `modules/platforms/shopee/components/navigation.py` | 可用 | 深链导航可用，但仍是轻量实现 |
| `shopee/date_picker` | `modules/platforms/shopee/components/date_picker.py` | 可用 | 通过 `RecipeExecutor` 复用，适合作为前置组件 |
| `shopee/orders_export` | `modules/platforms/shopee/components/orders_export.py` | 可用 | 具备导出与下载重试，但复杂度中等 |
| `shopee/products_export` | `modules/platforms/shopee/components/products_export.py` | 成熟 | 已覆盖“最新记录下载 / 文件系统兜底” |
| `shopee/analytics_export` | `modules/platforms/shopee/components/analytics_export.py` | 成熟 | 已覆盖“生成报告 / 最新下载按钮 / 重试与兜底” |
| `shopee/finance_export` | `modules/platforms/shopee/components/finance_export.py` | 可用 | 可复用，但复杂度低于 products/services |
| `shopee/services_export` | `modules/platforms/shopee/components/services_export.py` | 成熟 | 已覆盖“最新记录 / 状态轮询 / HAR/API 兜底” |

### 排除出 canonical 的文件

| 文件 | 原因 |
|------|------|
| `modules/platforms/shopee/components/export.py` | 通用基类薄封装，不应作为用户直接维护的业务导出组件 |
| `modules/platforms/shopee/components/metrics_selector.py` | skeleton only，明确不是成熟组件 |
| `modules/platforms/shopee/components/recorder_test_login.py` | 录制测试件，不应作为正式登录组件 |
| `modules/platforms/shopee/components/*_config.py` | 配置文件，不是逻辑组件入口 |

## TikTok

### Canonical 槽位

| 槽位 | 当前基础文件 | 成熟度 | 说明 |
|------|--------------|--------|------|
| `tiktok/login` | `modules/platforms/tiktok/components/login.py` | 成熟 | 已覆盖手机号登录、2FA、信任设备、复杂分支 |
| `tiktok/navigation` | `modules/platforms/tiktok/components/navigation.py` | 成熟 | 已覆盖 deep-link、空白页 watchdog、自愈刷新 |
| `tiktok/date_picker` | `modules/platforms/tiktok/components/date_picker.py` | 成熟 | 已覆盖 iframe、递归 roots、服务页特殊面板 |
| `tiktok/shop_switch` | `modules/platforms/tiktok/components/shop_switch.py` | 可用 | canonical 入口；当前内部仍委托 `shop_selector.py` 实现，后续应继续规范化 |
| `tiktok/export` | `modules/platforms/tiktok/components/export.py` | 成熟 | 已覆盖按钮禁用、tab 切换、确认按钮、全局下载监听 |

### 排除出 canonical 的文件

| 文件 | 原因 |
|------|------|
| `modules/platforms/tiktok/components/*_config.py` | 配置文件，不是逻辑组件入口 |
| `modules/platforms/tiktok/components/config_registry.py` | 注册中心，不是组件入口 |

## 妙手 Miaoshou

### Canonical 槽位

| 槽位 | 当前基础文件 | 成熟度 | 说明 |
|------|--------------|--------|------|
| `miaoshou/login` | `modules/platforms/miaoshou/components/login.py` | 可用 | 正式入口是 `login.py`，当前实现委托到 `miaoshou_login.py` |
| `miaoshou/navigation` | `modules/platforms/miaoshou/components/navigation.py` | 可用 | 兼容导航件，可作为最小前置，但仍偏轻量 |
| `miaoshou/date_picker` | `modules/platforms/miaoshou/components/date_picker.py` | 可用 | 已有快捷项与直接输入双路径，但仍需继续规范化 |
| `miaoshou/export` | `modules/platforms/miaoshou/components/export.py` | 成熟 | 已覆盖 dropdown / dialog / iframe / 下载 tap / 多级 fallback |

### 排除出 canonical 的文件

| 文件 | 原因 |
|------|------|
| `modules/platforms/miaoshou/components/miaoshou_login.py` | 历史生成实现，保留为 `login.py` 的底层实现细节，不应单独暴露给用户 |
| `modules/platforms/miaoshou/components/*_config.py` | 配置文件，不是逻辑组件入口 |
| `modules/platforms/miaoshou/components/overlay_guard.py` | 抗干扰工具件，不是逻辑组件入口 |

## 当前推荐迁移策略

### 直接作为迁移基础的成熟组件

- Shopee：
  - `products_export.py`
  - `analytics_export.py`
  - `services_export.py`
- TikTok：
  - `login.py`
  - `navigation.py`
  - `date_picker.py`
  - `export.py`
- 妙手：
  - `export.py`

### 可作为前置基础但后续仍需优化的组件

- Shopee：
  - `login.py`
  - `navigation.py`
  - `date_picker.py`
  - `orders_export.py`
  - `finance_export.py`
- TikTok：
  - `shop_switch.py`
- 妙手：
  - `login.py`
  - `navigation.py`
  - `date_picker.py`

## 使用建议

1. 后续“批量注册 Python 组件”时，应以本清单中的 canonical 槽位为目标。
2. 用户默认应只维护本清单中的 canonical 组件。
3. 排除列表中的文件不应作为默认编辑对象暴露给用户。
