# Semantic Field Rules

This document defines the active semantic-layer field unification rules for the PostgreSQL-first runtime.

The active repository rule entrypoint remains `AGENTS.md`.

This document is the temporary source of truth for explicit semantic field decisions before the rules are migrated into `core.field_alias_rules`.

## Core Rule

This rule applies to **all data domains**, not only `analytics` and `orders`.

### Iron Law

1. If two different fields coexist in the **same platform**, **same data domain**, and **same source file**, they must be treated as **different business metrics by default**.
2. Those coexisting fields must be **split**, not merged.
3. Cross-platform unification is allowed only when two fields from different platforms represent the same business semantic and are mapped into the system's canonical semantic field.

This means semantic unification is determined by:

- cross-platform business meaning
- explicit canonical mapping

It is **not** determined only by similar raw labels.

## Scope

This first rule set formalizes the current high-risk decisions for:

- `analytics`
- `orders`

Other domains may follow the same iron law and can be added later.

## Rule Types

### Split Rule

Use `split` when two fields coexist in the same platform/domain/file and represent distinct metrics.

### Merge Rule

Use `merge` when fields from different platforms represent the same business semantic and should map into one canonical field.

### Priority Rule

Use `priority` only inside a canonical merge group, and only for cross-platform alias resolution or fallback ordering.

Priority must never be used to collapse same-file coexisting metrics.

## Analytics Rules

Status: Implemented in `sql/semantic/analytics_atomic.sql` and `sql/semantic/analytics_monthly_atomic.sql` on 2026-05-26.

### Split Rules

| Platform | Domain | Raw Fields | Decision | Canonical Output |
|----------|--------|------------|----------|------------------|
| tiktok | analytics | `订单数`, `SKU 订单数` | split | `order_count`, `sku_order_count` |
| tiktok | analytics | `GMV`, `总成交额` | split | `gmv`, `total_transaction_amount` |

### Merge Rules

| Cross-Platform Semantic | Canonical Field | Accepted Raw Source Fields |
|-------------------------|-----------------|----------------------------|
| 交易总额 / GMV | `gmv` | TikTok `GMV`; Shopee analytics sales-like field explicitly confirmed as same semantic |
| 访客数 | `visitor_count` | `访客数`, `独立访客`, `uv`, `visitor_count`; TikTok analytics explicitly maps `商品访客数` to canonical `visitor_count` |
| 页面浏览量 | `page_views` | `浏览量`, `页面浏览数`, `页面浏览次数`, `page_views`, `views` |
| 订单数 | `order_count` | `订单数`, `订单数量`, `order_count`, `Order Count` excluding any field explicitly split such as `SKU 订单数` |

### Analytics Notes

- If TikTok analytics contains both `订单数` and `SKU 订单数` in the same file, semantic output must keep both metrics.
- If TikTok analytics contains both `GMV` and `总成交额` in the same file, semantic output must keep both metrics.
- Approved TikTok analytics rule: `页面浏览次数` is the canonical TikTok `page_views` source.
- Approved TikTok analytics rule: `商品访客数` is the canonical TikTok `visitor_count` source for dashboard PV/UV semantics.
- TikTok dashboard PV/UV semantics must prioritize `页面浏览次数` and `商品访客数` even when other visitor-like aliases coexist in the same export.
- `product_visitor_count` remains available as a compatibility field, but TikTok dashboard consumers reading canonical `visitor_count` must receive `商品访客数`.
- Approved Shopee analytics rule: `页面浏览数` maps to canonical `page_views`, and `访客数` maps to canonical `visitor_count`.

## Orders Rules

Status: Partially implemented on 2026-05-26. The first-wave `orders_atomic.sql` boundary cleanup now keeps payment fields out of `sales_amount` and preserves RMB-first profit behavior. Full domain closure still remains pending.

### Merge Rules

| Cross-Platform Semantic | Canonical Field | Accepted Raw Source Fields |
|-------------------------|-----------------|----------------------------|
| 销售额 | `sales_amount` | `销售额`, `销售金额`, `sales_amount`, `Sales Amount` |
| 实付金额 | `paid_amount` | `实付金额`, `买家实付金额`, `paid_amount`, `Paid Amount` |
| 利润 | `profit` | `利润`, `profit`, `Profit` |
| 订单原始金额 | `order_original_amount` | `订单原始金额`, `order_original_amount`, `Order Original Amount` |
| 平台佣金 | `platform_commission` | `平台佣金`, `platform_commission`, `Platform Commission` |

### Confirmed Boundary Rules

| Canonical Field | Confirmed Source Fields |
|-----------------|-------------------------|
| `paid_amount` | `实付金额`, `买家实付金额`, `买家支付`, `买家支付(RMB)`, `buyer_payment`, `buyer_payment_rmb` |
| `sales_amount` | `销售额`, `销售金额`, `GMV`, `订单金额`, `成交金额`, `总收入` |
| `profit` | `利润`, `利润(RMB)`, `profit`, `profit_rmb`, `毛利`, `Profit` |

### Priority Rules

These priority rules are valid because they resolve cross-platform or cross-export aliases into one canonical business field, not same-file coexisting metrics.

| Canonical Field | Priority Order |
|-----------------|----------------|
| `profit` | `利润(RMB)` > `profit_rmb` > `利润` > `profit` |
| `paid_amount` | `buyer_payment_rmb` / RMB-equivalent confirmed field > `实付金额` / local-currency equivalent fallback |
| `platform_commission` | RMB-specific confirmed field > local-currency field fallback |

### Orders Notes

- Orders semantic rules may prefer RMB-backed values over local-currency values when that preference is already a confirmed business rule.
- This does not violate the iron law, because RMB vs local-currency variants here are system-defined canonical priority resolution rules, not two unrelated coexisting business metrics that must both survive as separate semantic outputs.
- Orders is the next domain to close after analytics. Review targets:
  - RMB priority chains
  - any same-file coexisting order metrics that are currently implicitly merged
  - whether `orders_monthly_atomic_mv` needs the same explicit field-boundary cleanup

## Explicit Non-Rules

The system must **not** assume any of the following without an explicit approved semantic rule:

- similar Chinese labels imply same business metric
- same English translation implies same business metric
- same numeric type implies same business metric
- same-file coexisting columns should be merged because values are “often close”

## Products Rules

Status: Partially implemented on 2026-05-26. The first-wave alias-only rules for Shopee products “已付款订单 / 已确认订单 / 已确定订单” semantic variants are now explicitly reflected in `sql/semantic/products_atomic.sql`.

### Merge Rules

| Canonical Field | Accepted Raw Source Fields |
|-----------------|----------------------------|
| `sales_amount` | `销售额（已付款订单）`, `销售额（已确认订单）`, `销售额（已确定订单）`, `销售额`, `销售金额`, `sales_amount`, `revenue` |
| `order_count` | `已付款订单`, `已确认订单`, `已确定订单`, `订单数`, `订单数量`, `order_count`, `orders` |
| `sales_volume` | `件数（已付款订单）`, `件数（已确认订单）`, `件数（已确定订单）`, `销量`, `销售数量`, `sales_volume`, `qty` |
| `conversion_rate` | `转化率（已付款订单）`, `转化率（已确认订单）`, `转化率（已确定订单）`, `转化率`, `conversion_rate`, `CVR` |

### Products Notes

- `products` 当前按历史已确认 alias-only 规则处理，不按拆分域处理。
- 如果未来发现同平台、同数据域、同文件中存在真正并存且不同义的 products 字段，再按全域铁律新增 split 规则。

## Services Rules

Status: Partially implemented on 2026-05-26. First-wave split rule now keeps `买家数` out of `order_count` and exposes independent `buyer_count` in `sql/semantic/services_atomic.sql`.

### Split Rules

| Platform | Domain | Raw Fields | Decision | Canonical Output |
|----------|--------|------------|----------|------------------|
| all | services | `订单数`, `买家数` | split | `order_count`, `buyer_count` |

## Inventory Rules

Status: Audited as low-risk on 2026-05-26. Current semantic mapping is sufficiently structured for this phase, and no first-wave same-file coexisting metric conflict requiring explicit split rules was identified.

### Inventory Notes

- Current inventory semantic mapping already exposes distinct stock-state fields such as:
  - `available_stock`
  - `on_hand_stock`
  - `reserved_stock`
  - `in_transit_stock`
  - `stockout_qty`
  - `reorder_point`
  - `safety_stock`
  - `unit_cost`
  - `inventory_value`
- This phase does not require additional inventory split/merge SQL changes.
- If future inventory files introduce same-platform, same-domain, same-file coexisting fields with ambiguous semantics, the all-domain iron law still applies and explicit split rules must be added.

## Relationship To Raw Layer

The raw layer must preserve source distinctions.

This document only governs:

- semantic-layer merge groups
- semantic-layer split decisions
- semantic-layer fallback priority

It must not be used to justify raw-layer column collapse.

## Relationship To Future Rule-Table Migration

This document is the pre-migration source of truth.

When migrated into `core.field_alias_rules`, the migration must preserve:

- the iron law
- split-vs-merge distinction
- explicit priority order
- domain/platform scope

If a future rule-table model cannot represent split rules and same-file coexistence guards, the schema must be extended before migration.
