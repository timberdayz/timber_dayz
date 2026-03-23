# Canonical 组件真实链路问题清单

本文档用于记录当前 canonical 采集组件在真实页面链路上的高优先级问题，作为后续优化顺序依据。

## 优先级说明

- `P0`：直接影响 canonical 组件在真实链路中的可靠性，应优先修复
- `P1`：不一定每次都会触发，但一旦触发会明显增加排障成本
- `P2`：优化项或进一步稳健性增强

---

## Shopee

### `shopee/products_export`

- `P0` 最新导出记录识别仍需真实页面验证  
  当前已经补了处理状态词识别与 `ExportResult` 契约，但仍需在真实页面验证：
  - 是否总能拿到最新记录
  - 是否会误点击历史记录
  - 文件系统兜底是否与 UI 下载监听一致

- `P1` “生成报告/立即生成”按钮触发后页面刷新节奏  
  当前已有 `_maybe_generate_report()`，但还需要确认：
  - 生成后下载入口是否稳定出现在预期容器
  - 等待窗口是否足够覆盖慢页面

### `shopee/services_export`

- `P0` 最新记录筛选仍需真实页面验证  
  当前已修：
  - `subtype` 过滤
  - 关键 `.count()` 的 `await`
  但仍需验证：
  - `ai_assistant` 与 `agent` 记录是否在真实页面中存在更多文本变体
  - 首条记录是否总是最新导出记录

- `P0` 下载入口候选仍偏宽  
  当前选择器较多，能覆盖更多 UI，但仍需真实页面确认：
  - 是否会抓到历史下载按钮
  - 是否需要更强的“最新记录范围内下载按钮”约束

- `P1` API fallback 链路仍需单独验证  
  当前已有 HAR/API fallback，但未纳入当前回归测试覆盖。

### `shopee/analytics_export`

- `P1` 最新下载入口等待策略需进一步对齐 services/products  
  当前已经修了 `ExportResult` 契约和 `count()` await，但仍建议继续验证：
  - “立即下载”
  - “生成后下载”
  - “目录即时检测”
  三条路径是否都能在真实页面上稳定命中

---

## TikTok

### `tiktok/export`

- `P0` 无数据禁用按钮跳过逻辑需要更多真实页面验证  
  当前逻辑会在 `/service-analytics` 且检测到 disabled 时返回：
  - `skip: service analytics has no data (export disabled)`
  还需要验证：
  - 是否只在无数据场景触发
  - 是否会误判“页面还没加载完”的暂时禁用态

- `P0` Tab 切换后导出按钮链路需更深验证  
  当前会切到“聊天详情”再导出，但还没验证：
  - 切换后是否一定稳定出现导出按钮
  - 是否需要更明确的页面 ready probe

- `P1` 二次确认按钮链路仍然偏宽  
  当前会在导出后尝试多个确认按钮：
  - `确认`
  - `确定`
  - `导出`
  - `Export`
  还需确认会不会误点页面其他按钮。

---

## 妙手 Miaoshou

### `miaoshou/export`

- `P0` dropdown / dialog / iframe 复合链路仍需进一步收口  
  当前已经修掉：
  - 无效 `.count()` 判断
  - 未 `await` 的 `.count()`
  - 未清理的 context download 监听器
  但其核心复杂度仍在：
  - 悬停后 dropdown 是否真正保持展开
  - `导出全部订单` / `导出搜索的商品` 菜单项是否总能命中
  - dialog footer 中 `导出` 按钮是否需要更强作用域约束
  - iframe fallback 是否过宽

- `P0` 多级 fallback 过多，需要逐步减法  
  当前为了提高命中率，保留了大量：
  - `hover`
  - `Enter`
  - `dispatch_event`
  - JS click
  - 鼠标坐标点击
  这些策略是成熟经验，但也意味着后续要逐步识别哪些 fallback 真实需要，哪些可以去掉。

- `P1` 日期相关前置链路需要真实页面复验  
  当前导出链路中仍有“重置时间 / 清空时间 / 直接填输入框”几种路径并存，需要在真实页面上验证哪条才是长期稳定路径。

---

## 组合链路状态

当前已具备最小组合级回归：

- `shopee/login + products_export`
- `tiktok/login + shop_switch + export`
- `miaoshou/login + export`

这些回归证明 canonical 组件在当前 adapter 路径中可组合，但**还不等于真实页面全量通过**。

---

## 建议顺序

1. `miaoshou/export`  
   原因：复杂度最高，包含 hover / dropdown / dialog / iframe 多链路问题。

2. `shopee/services_export`  
   原因：存在 subtype 区分与最新记录选择问题，业务风险最高。

3. `tiktok/export`  
   原因：需要继续压实“禁用按钮 = 无数据”与 tab 切换后的导出链路。

4. `shopee/products_export` / `shopee/analytics_export`  
   原因：基础契约已较稳定，适合后续做真实页面精修。
