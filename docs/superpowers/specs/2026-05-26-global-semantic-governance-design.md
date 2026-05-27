# Global Semantic Governance Design

**Goal**

为 `orders / analytics / products / inventory / services` 五个数据域建立统一的 semantic 字段治理框架，确保 raw 层保真、semantic 层显式统一，并以 `analytics` 作为第一批完整落地域完成规则打样。

**Current Problem**

- 现有 raw -> semantic 链路长期存在隐式字段归并，部分规则散落在 Python 归一化逻辑、template 逻辑和 `sql/semantic/*.sql` 的 `COALESCE` 链中。
- 这种隐式规则容易把“同文件并存字段”和“跨平台同义字段”混为一谈，导致：
  - raw 层字段被过早压缩
  - semantic 口径缺乏统一的显式来源
  - 新字段、新平台、新模板接入时容易重复出错
- 仓库中已经有一批历史 semantic 规则和 alias-only 治理经验，但还没有形成统一的全域治理框架。

## Design Principles

### 1. Raw First, Semantic Later

- `b_class raw` 只负责保留原始字段和文件级元数据
- `semantic` 层负责统一业务口径
- `mart / api` 只消费 semantic 后的稳定字段

### 2. Iron Law For All Domains

适用于所有数据域：

1. 如果两个不同字段在**同平台、同数据域、同文件**中并存，则默认视为**不同业务指标**
2. 这类字段必须 **split**，不能合并
3. 只有**跨平台**且**业务语义一致**的字段，才能在 semantic 层归并到 canonical 字段

### 3. Explicit Rule Types

每个 semantic 字段规则必须属于以下三类之一：

- `split`
  - 同文件并存字段的拆分规则
- `merge`
  - 跨平台同义字段归并规则
- `priority`
  - 同一 canonical 字段内部的 fallback 优先级规则

### 4. Single Active Rule Source By Phase

在迁移到规则表前：

- 文档是设计与审阅基线
- SQL 是运行时执行基线

后续迁入 `core.field_alias_rules` 时，必须保持与文档/SQL 一致，不得引入平行规则体系。

## Scope

### This Phase

本阶段覆盖：

- 全域统一治理框架（5 个数据域）
- `analytics` 第一域详细规则
- `orders` 第二优先域的治理边界确认

### Later Phases

后续域按顺序推进：

1. `analytics`
2. `orders`
3. `products`
4. `services`
5. `inventory`

## Canonical Domain Workflow

```text
catalog_files
-> data_sync router
-> data_sync_service
-> data_ingestion_service
-> b_class raw
-> semantic rule application
-> semantic.fact_<domain>_atomic
-> mart
-> api_modules
-> backend
-> frontend
```

## Domain Governance Framework

### Orders

Governance mode:

- raw 层保留订单原始字段
- semantic 层允许金额/货币字段按已确认业务口径做 merge 和 priority

Typical canonical fields:

- `sales_amount`
- `paid_amount`
- `profit`
- `order_original_amount`
- `platform_commission`
- `platform_deduction_fee`
- `platform_voucher`
- `platform_service_fee`
- `product_quantity`
- `buyer_count`

Orders-specific note:

- RMB 优先的 priority 规则继续允许存在
- 但不能被误用为“同文件并存不同业务指标”的吞并逻辑

### Analytics

Governance mode:

- 这是当前最高风险域
- 必须先停止隐式 COALESCE 误合并
- 需要把拆分规则和跨平台 merge 规则显式写出

Confirmed split rules:

| Platform | Domain | Raw Fields | Decision | Canonical Output |
|----------|--------|------------|----------|------------------|
| tiktok | analytics | `订单数`, `SKU 订单数` | split | `order_count`, `sku_order_count` |
| tiktok | analytics | `GMV`, `总成交额` | split | `gmv`, `total_transaction_amount` |
| tiktok | analytics | `访客数`, `商品访客数` | split | `visitor_count`, `product_visitor_count` |

Confirmed merge directions:

| Cross-Platform Semantic | Canonical Field | Candidate Source Fields |
|-------------------------|-----------------|-------------------------|
| 交易总额 / GMV | `gmv` | TikTok `GMV`; Shopee analytics sales-like field confirmed as same business semantic |
| 页面浏览量 | `page_views` | `浏览量`, `页面浏览数`, `页面浏览次数`, `page_views`, `views` |
| 订单数 | `order_count` | `订单数`, `订单数量`, `order_count`, `Order Count` excluding explicit split fields |

Analytics-specific rule:

- `商品访客数` 只有在它**不是同文件并存字段**时，才允许进入跨平台 merge 讨论
- 如果与 `访客数` 同时出现，则必须拆分

### Products

Governance mode:

- 继承已有 `products semantic alias` 先例
- 优先处理“标签变化但语义相同”的 alias-only 规则

Known precedent:

- `已付款订单 / 已确认订单 / 已确定订单` 这一类已存在历史设计先例
- products 适合先走 alias-only 规则而不是立即扩大拆分面

### Services

Governance mode:

- 服务域通常字段数较少，但容易与 analytics/products 共用名字
- 必须严格按同文件并存规则拆分
- 再做跨平台 merge

### Inventory

Governance mode:

- 通常结构化程度更高
- 拆分/merge 风险相对低
- 仍必须遵守同文件并存字段默认拆分

## Analytics First-Domain Implementation Direction

### Current Runtime Problem

`analytics_atomic.sql` 当前隐式规则存在：

- `订单数 / 订单数量 / order_count -> order_count_raw`
- `成交金额 / GMV / gmv / sales_amount -> gmv_raw`
- `访客数 / 独立访客 / uv / visitor_count / ... -> visitor_count_raw`

这些规则没有显式区分：

- 同平台同文件并存字段
- 跨平台可合并字段

### Required Refactor

`analytics_atomic.sql` 与 `analytics_monthly_atomic.sql` 的第一阶段改造目标：

1. 保留现有稳定 canonical 输出：
   - `gmv`
   - `order_count`
   - `visitor_count`
   - `page_views`
2. 新增显式拆分字段：
   - `sku_order_count`
   - `total_transaction_amount`
   - `product_visitor_count`
3. 将现有 `COALESCE` 规则改为：
   - canonical merge rules only for cross-platform semantic equivalence
   - explicit split fields never feed the wrong canonical field

### Analytics SQL Rule Shape

Target shape:

- `gmv_raw`
  - 仅来自已确认属于 canonical `gmv` 的跨平台字段
- `total_transaction_amount_raw`
  - 单独映射 `总成交额`
- `order_count_raw`
  - 不再吞并 `SKU 订单数`
- `sku_order_count_raw`
  - 单独映射 `SKU 订单数`
- `visitor_count_raw`
  - 不再在同文件并存场景中吞并 `商品访客数`
- `product_visitor_count_raw`
  - 单独映射 `商品访客数`

## Relationship To Existing Alias Rule Assets

Existing assets:

- `sql/ops/create_field_alias_rules.sql`
- `backend/services/field_alias_rule_service.py`

Decision for this phase:

- 不直接迁移到规则表
- 先由文档 + semantic SQL 收口
- 等 `analytics/orders/products/services/inventory` 的显式规则稳定后，再迁移到 `core.field_alias_rules`

## Deliverables

### Phase A: Governance Baseline

- `docs/architecture/SEMANTIC_FIELD_RULES.md`
- `docs/architecture/DATA_SYNC_CONTRACT.md`
- `docs/architecture/BOUNDARIES.md`

### Phase B: Analytics Closure

- `sql/semantic/analytics_atomic.sql`
- `sql/semantic/analytics_monthly_atomic.sql`
- 对应 `backend/tests/data_pipeline/*` 测试更新

Status: Implemented on 2026-05-26. `analytics` now explicitly splits:

- `订单数` vs `SKU 订单数`
- `GMV` vs `总成交额`
- `访客数` vs `商品访客数`

### Phase C: Orders Closure

- `sql/semantic/orders_atomic.sql`
- `sql/semantic/orders_monthly_atomic.sql`
- 对应 data pipeline 测试更新

Status: In progress on 2026-05-26. First-wave closure completed for:

- `paid_amount` payment-field boundary
- `sales_amount` sales-field boundary
- `profit` RMB-first priority preservation

Remaining follow-up:

- audit `orders_monthly_atomic_mv` and monthly closure consistency
- review any same-file coexisting order-side metrics beyond the current first-wave fields

### Phase D: Remaining Domains

- `products`
- `services`
- `inventory`

Status update on 2026-05-26:

- `products` first-wave alias-only closure implemented in `sql/semantic/products_atomic.sql`
- `services` first-wave split closure implemented for `order_count` vs `buyer_count`
- `inventory` audited as low-risk; no first-wave SQL changes required

## Non-Goals

- 这一阶段不直接把规则迁入数据库规则表
- 不一次性重写所有 mart/api SQL
- 不做历史 raw 数据回填
- 不在没有显式业务确认时擅自合并同文件并存字段

## Success Criteria

1. 所有数据域都遵守统一铁律
2. `analytics` 的拆分字段和 merge 字段在 SQL 中显式可见
3. 不再因为同文件并存字段被误合并而导致语义污染
4. 后续迁移到规则表时，文档与 SQL 能一一对应
