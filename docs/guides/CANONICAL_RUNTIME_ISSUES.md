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

### `miaoshou/orders_export`

- `P0` 订单状态筛选下拉框同样存在 `jx-select` 透明占位层拦截点击的问题  
  2026-10-23 排查库存域失败时发现同类故障：订单状态 `filters.py` 的点击会被
  `jx-select__selected-item jx-select__placeholder is-transparent` 拦截命中测试，
  抛 `Locator.click: Timeout 1500ms exceeded`。  
  该修复一度以未提交改动留在工作区，并打挂了 4 个既有单元测试（假对象不支持
  `force=` 关键字，异常被 `except Exception` 吞掉），2026-10-23 已随 `162f8bb0`
  修好入库，并改用 DOM 结构判定「是否已全选」。

### `miaoshou/inventory_export`

- `P0` 仓库范围下拉框被 `jx-select` 透明占位层拦截点击，线上任务失败  
  2026-10-23 11:56:35 任务失败，耗时 44s（含 23s 等验证码）。直接根因：
  `modules/platforms/miaoshou/components/warehouse_filters.py` 点击仓库范围下拉框时，
  `jx-select__selected-item jx-select__placeholder is-transparent` 拦截命中测试 →
  `Locator.click: Timeout 1500ms exceeded`。  
  证据：
  - `logs/backend-local.out.log:364-389`
  - `core.collection_tasks` id=637
  - `core.collection_task_logs` id=3984  
  域隔离：同期 task 636（`orders`）状态为 `completed`，域之间互不影响。

- `P0` 该故障是 flaky，非必现  
  同一数据域历史上成功过（2026-09-14，见
  `docs/superpowers/plans/2026-10-21-inventory-aging-pipeline-recovery.md` 第 1008 行），
  因此问题长期未被提前发现。  
  整改方向见
  `docs/superpowers/specs/2026-10-23-miaoshou-inventory-domain-remediation-design.md` §5.2 L1-1
  （仓库范围下拉框 C→A→B→D 四层遮挡防护）。

- `P0` **真实页面取证（2026-10-23）推翻了此前的两个假设**  
  人工登录妙手后用 CDP 探针取到仓库清单页的真实 DOM，结论如下：

  1. **「勾全选」这个动作从来没有真正成功过**。浮层有两个可选根：
     外层 `div.jx-select-dropdown` 与内层 `ul.jx-select-dropdown__list[role=listbox]`
     （`aria-controls` 指向的是内层 `ul`）。历史实现把 `get_by_role("listbox")`
     排在浮层候选**第一位**，于是拿到内层 `ul`——而「全选」复选框在**外层**
     `div.jx-select-dropdown__header` 里，`ul` 内命中数为 **0**。
     实测命中计数：`get_by_role("checkbox", name="全选")` = **0**；
     `.jx-select-dropdown__header .jx-checkbox` 在外层 = **1**、在内层 `ul` = **0**。
     这解释了为什么 2026-10-21 那次成功入库其实走的是**空态**。

  2. **仓库筛选是可选筛选项，「不选 = 全选」**。空态（显示「请选择」）与
     全选态（显示 `菲律宾3店-时尚箱包 × + 4`）的 SKU 总数（**1113**）、
     分页（**56 页**）与表格「仓库」列内容**完全一致**，且空态的「仓库」列
     本来就是跨仓库混合的。证据：
     `output/playwright/work/miaoshou/inventory_scope/02-warehouse-page.png`（空态）
     与 `1-open.png`（全选态）。

  3. 因此**「显式勾全选」失败不应阻断整个采集任务**——它只是一个可选的
     UI 交互，数据范围不受影响。2026-10-23 起该失败降级为告警 + 留痕
     （`details.scope_all_selected=false` + 降级原因 + 截图），不再让任务整体失败。

  4. 附带取证结论：仓库筛选字段有**稳定锚点** `[data-field='warehouseIds']`
     （与订单域 `[data-field='appOrderStatus']` 同款），不再需要靠「仓库」
     文案猜最近祖先；仓库 select 根节点带 `modelvaluegroup` 属性
     （全选态 = `684506,563787,563786,381635,299699`，空态 = 空串），
     可直接作为「是否已全选」的判据；「全选」复选框的**可点击目标是
     `label.jx-checkbox`**——真实 input 的 class 是 `jx-checkbox__original`
     （**不是**归档脚本里的 `jx-checkbox__input`），且它**虽然能定位却点不到**
     （视觉隐藏，Playwright actionability 超时）；**层 D 键盘兜底实测有效**
     （焦点落到 `input.jx-select__input` 后按 `Enter`，`aria-expanded` 由
     `false` 变 `true`，浮层真的弹出）。

  5. **端到端验证（2026-10-23，在人工登录的真实页面上直接跑组件）**：
     刷新页面 → 空态（`modelvaluegroup=""`）→ 跑 `MiaoshouWarehouseFilters`
     → 组件自行开下拉、点中「全选」、post-check 回读确认 →
     `modelvaluegroup` 变为 `684506,563787,563786,381635,299699`、
     `.jx-tag` 变为 `["菲律宾3店-时尚箱包", "+ 4"]`；再跑一次命中 pre-check 被跳过。
     **即：修复后的「勾全选」在真实页面上第一次就走通了**（此前从未成功过）。
     同时实测发现「点击 wrapper 是 toggle 语义」——浮层已开着时再点会把它关掉，
     故层 A 点击前先做「浮层是否已可见」检测，已可见则直接复用。

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
