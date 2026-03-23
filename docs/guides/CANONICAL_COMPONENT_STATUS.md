# Canonical 组件阶段性状态

本文档用于记录当前 canonical 采集组件的阶段性状态，帮助后续判断：

- 哪些组件已经适合进入“用户测试 / 继续优化”阶段
- 哪些组件还处于“结构已收口，但真实页面链路仍需继续修复”阶段
- 下一步优先修哪些组件最划算

## 状态定义

- **可测试**：已完成规则收口、基础契约修复、组合级最小链路回归，可以进入用户测试与进一步优化
- **继续修**：已收口为 canonical，但真实页面链路问题仍较多，需要优先继续修
- **辅助件**：前置组件或内部实现，不是用户直接维护的主导出组件

---

## Shopee

| 组件 | 当前状态 | 说明 |
|------|----------|------|
| `shopee/login` | 可测试 | 已是 canonical 正式入口，适合作为组合链路起点 |
| `shopee/navigation` | 可测试 | 轻量实现，但在当前架构下可作为前置组件使用 |
| `shopee/date_picker` | 可测试 | 通过 `RecipeExecutor` 复用，当前主要是前置件 |
| `shopee/products_export` | 可测试 | `ExportResult` 契约、处理中状态识别已修，已具备最小组合回归 |
| `shopee/analytics_export` | 继续修 | 基础契约已修，但真实页面下载入口等待链路还需深挖 |
| `shopee/services_export` | 继续修 | 语法、契约、subtype 匹配、await 问题已修，但真实业务链路仍最复杂 |
| `shopee/orders_export` | 可测试 | 当前复杂度相对较低，适合作为次级复用组件 |
| `shopee/finance_export` | 可测试 | 当前复杂度相对较低，适合作为次级复用组件 |

### 不应作为默认维护对象
- `modules/platforms/shopee/components/export.py`
- `modules/platforms/shopee/components/metrics_selector.py`
- `modules/platforms/shopee/components/recorder_test_login.py`
- `modules/platforms/shopee/components/*_config.py`

---

## TikTok

| 组件 | 当前状态 | 说明 |
|------|----------|------|
| `tiktok/login` | 可测试 | 当前 canonical 登录入口，基础行为完整 |
| `tiktok/navigation` | 可测试 | deep-link + watchdog 已具备 |
| `tiktok/date_picker` | 可测试 | iframe 和日期面板策略已较完整 |
| `tiktok/shop_switch` | 可测试 | canonical 入口已建立，当前内部委托 `shop_selector` |
| `tiktok/export` | 继续修 | 已修 manifest `shop_region`、数据域口径、结果契约、监听器清理，但真实 UI 行为仍需继续压实 |

### 不应作为默认维护对象
- `modules/platforms/tiktok/components/shop_selector.py`
- `modules/platforms/tiktok/components/*_config.py`
- `modules/platforms/tiktok/components/config_registry.py`

---

## 妙手 Miaoshou

| 组件 | 当前状态 | 说明 |
|------|----------|------|
| `miaoshou/login` | 可测试 | 成功判定已修，不再停留 TODO 状态 |
| `miaoshou/navigation` | 可测试 | 当前可作为轻量前置组件 |
| `miaoshou/date_picker` | 可测试 | 可作为前置组件，但后续仍需真实页面收敛 |
| `miaoshou/export` | 继续修 | 已修数据域口径、download await、count 判断、context download 清理，但 dropdown/dialog/iframe 复合链路仍最复杂 |

### 不应作为默认维护对象
- `modules/platforms/miaoshou/components/miaoshou_login.py`
- `modules/platforms/miaoshou/components/*_config.py`
- `modules/platforms/miaoshou/components/overlay_guard.py`

---

## 当前组合级状态

已具备最小组合回归：

- `shopee/login + products_export`
- `tiktok/login + shop_switch + export`
- `miaoshou/login + export`

说明：
- 这些组合说明 canonical 组件在当前 adapter 路径下已经能组合执行
- 但这还不等于真实页面全量通过，只能说明“当前架构上的正式链路已经开始成立”

---

## 当前推荐顺序

1. `shopee/services_export`
2. `miaoshou/export`
3. `tiktok/export`
4. `shopee/analytics_export`

原因：
- `services_export` 业务链路风险最高
- `miaoshou/export` 页面交互复杂度最高
- `tiktok/export` 还需继续验证无数据禁用态与 tab 链路
- `analytics_export` 当前基础契约较稳，可放在后面精修
