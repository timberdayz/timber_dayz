# Business Overview Metric Lineage

This guide documents the current metric lineage for the Business Overview experience in the PostgreSQL-first runtime.

The goal is practical:

- make verification faster
- make regressions easier to diagnose
- make semantic-rule changes safer

## Scope

This guide covers the core Business Overview metrics currently exposed through:

- `api.business_overview_kpi_module`
- `api.business_overview_comparison_module`
- `api.business_overview_operational_metrics_module`
- `api.business_overview_shop_racing_module`
- `api.business_overview_traffic_ranking_module`

## Canonical Rule

Business Overview uses the PostgreSQL chain:

```text
semantic -> mart -> api_modules -> postgresql_dashboard_service -> frontend
```

When verifying a Business Overview number, always trace it through this chain instead of checking frontend labels alone.

## Core Metrics

### 1. Sales Amount

**Business meaning in current UI:** 销售额

**Current SQL lineage:**

```text
semantic.fact_orders_atomic / semantic.fact_orders_monthly_atomic
  -> paid_amount
  -> mart.*_kpi.gmv = SUM(paid_amount)
  -> api.business_overview_* exposes that gmv
  -> frontend displays it as sales amount / 销售额
```

**Current runtime truth:**

- Business Overview sales amount is sourced from `paid_amount`, not `sales_amount`
- This matches the current business decision that real sales should come from RMB-backed actual payment fields

**Primary assets:**

- `sql/semantic/orders_atomic.sql`
- `sql/semantic/orders_monthly_atomic.sql`
- `sql/mart/shop_day_kpi.sql`
- `sql/mart/shop_week_kpi.sql`
- `sql/mart/shop_month_kpi.sql`
- `sql/mart/platform_month_kpi.sql`

### 2. Order Count

**Business meaning in current UI:** 订单数

**Current SQL lineage:**

```text
semantic.fact_orders_atomic / semantic.fact_orders_monthly_atomic
  -> order_id
  -> mart.*_kpi.order_count = COUNT(DISTINCT order_id)
  -> api.business_overview_* consumes order_count
```

**Current runtime truth:**

- Business Overview order count is not taken from raw numeric order-count columns
- It is aggregated from distinct semantic order identifiers

**Primary assets:**

- `sql/semantic/orders_atomic.sql`
- `sql/semantic/orders_monthly_atomic.sql`
- `sql/mart/shop_day_kpi.sql`
- `sql/mart/shop_week_kpi.sql`
- `sql/mart/shop_month_kpi.sql`

### 3. Traffic

**Business meaning in current UI:** 流量

**Current SQL lineage:**

```text
semantic.fact_analytics_atomic / semantic.fact_analytics_monthly_atomic
  -> visitor_count
  -> page_views
  -> mart.*_kpi keeps both
  -> api.business_overview_* usually uses COALESCE(page_views, visitor_count)
```

**Current runtime truth:**

- Business Overview traffic is not a single semantic field
- It currently prefers `page_views`
- It falls back to `visitor_count` when `page_views` is absent

**Operational risk:**

- This is one of the highest-risk metric families for future semantic changes
- Any rule change in `page_views`, `visitor_count`, or related analytics fields can affect:
  - traffic
  - conversion rate

**Primary assets:**

- `sql/semantic/analytics_atomic.sql`
- `sql/semantic/analytics_monthly_atomic.sql`
- `sql/mart/shop_day_kpi.sql`
- `sql/mart/shop_week_kpi.sql`
- `sql/mart/shop_month_kpi.sql`
- `sql/api_modules/business_overview_kpi_module.sql`
- `sql/api_modules/business_overview_comparison_module.sql`

### 4. Conversion Rate

**Business meaning in current UI:** 转化率

**Current SQL lineage:**

```text
mart.*_kpi
  -> order_count
  -> COALESCE(page_views, visitor_count)
  -> conversion_rate = order_count / traffic
  -> api.business_overview_* consumes conversion_rate
```

**Current runtime truth:**

- Business Overview conversion rate is not simply the raw exported conversion-rate field
- It is recomputed from Business Overview’s current traffic denominator

**Implication:**

- If `traffic` changes, `conversion_rate` changes too
- Traffic semantic changes must always be reviewed together with conversion-rate expectations

**Primary assets:**

- `sql/mart/shop_day_kpi.sql`
- `sql/mart/shop_week_kpi.sql`
- `sql/mart/shop_month_kpi.sql`
- `sql/mart/platform_day_kpi.sql`
- `sql/mart/platform_month_kpi.sql`

### 5. Profit

**Business meaning in current UI:** 利润

**Current SQL lineage:**

```text
semantic.fact_orders_atomic / semantic.fact_orders_monthly_atomic
  -> profit
  -> mart.*_kpi.profit = SUM(profit)
  -> api.business_overview_* consumes profit
```

**Current runtime truth:**

- Business Overview profit comes from semantic `profit`
- Current governance expects RMB-priority logic to remain active for `orders.profit`

**Primary assets:**

- `sql/semantic/orders_atomic.sql`
- `sql/semantic/orders_monthly_atomic.sql`
- `sql/mart/shop_day_kpi.sql`
- `sql/mart/shop_week_kpi.sql`
- `sql/mart/shop_month_kpi.sql`

## Metrics Not Currently Directly Used By Business Overview Core

These semantic fields exist and are valuable, but are not currently direct core Business Overview inputs in the main path:

- `purchase_amount`
- `warehouse_operation_fee`
- `platform_commission`
- `platform_deduction_fee`
- `platform_voucher`
- `platform_service_fee`
- `analytics.total_transaction_amount`
- `analytics.sku_order_count`
- `analytics.product_visitor_count`
- `services.buyer_count`

They may still affect:

- side modules
- cost analysis
- future Business Overview enrichments

## Verification Checklist

When a Business Overview number looks wrong, verify in this order:

1. Confirm the UI metric label and exact module.
2. Confirm the API module/view used by that module.
3. Confirm the mart field used by that API view.
4. Confirm the semantic field feeding that mart field.
5. Confirm the raw fields behind that semantic field.

## High-Risk Change Zones

The following changes require explicit Business Overview re-verification:

- any change to `orders.paid_amount`
- any change to `orders.profit`
- any change to `analytics.page_views`
- any change to `analytics.visitor_count`
- any change to `analytics` traffic split/merge rules
- any mart change touching `gmv`, `order_count`, `visitor_count`, `conversion_rate`, or `profit`

## Short Summary

For current Business Overview:

- 销售额 = `paid_amount` aggregation path
- 订单数 = `COUNT(DISTINCT order_id)`
- 流量 = `COALESCE(page_views, visitor_count)`
- 转化率 = `order_count / traffic`
- 利润 = `profit` aggregation path
