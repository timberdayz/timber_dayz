# PostgreSQL Dashboard Calculation Audit Playbook

## Scope

This audit playbook covers the active PostgreSQL Dashboard runtime chain and the annual-cost-style modules that depend on GMV/profit semantics.

Covered runtime routes and modules:

- `business_overview_kpi`
- `business_overview_comparison`
- `business_overview_shop_racing`
- `business_overview_traffic_ranking`
- `business_overview_inventory_backlog`
- `business_overview_operational_metrics`
- `clearance_ranking`
- `annual_summary_kpi`
- `annual_summary_trend`
- `annual_summary_platform_share`
- `annual_summary_by_shop`
- `annual_summary_target_completion`
- annual cost aggregate service: `backend/services/annual_cost_aggregate.py`

Note: repository discussions sometimes describe this scope as "11 modules", but the current PostgreSQL router surface in `backend/routers/dashboard_api_postgresql.py` exposes the 12 dashboard routes listed above. This playbook audits the concrete code surface, not the shorthand count.

## Goal

Use one repeatable checklist to answer three questions:

1. Are negative values, especially refund/return-driven profit negatives, preserved correctly from `b_class` through to frontend payloads?
2. For each data domain, what exact objects and formulas feed the frontend?
3. How do we prove a dashboard number is correct, and where do we look first when it is not?

## Architecture Baseline

The active runtime chain is:

`b_class raw -> semantic -> mart -> api -> backend -> frontend`

Key code anchors:

- Raw ingest: `backend/routers/field_mapping_ingest.py`, `backend/services/raw_data_importer.py`
- Semantic SQL: `sql/semantic/*.sql`
- Mart SQL: `sql/mart/*.sql`
- API module SQL: `sql/api_modules/*.sql`
- Service layer: `backend/services/postgresql_dashboard_service.py`
- Router layer: `backend/routers/dashboard_api_postgresql.py`
- Frontend API client: `frontend/src/api/dashboard.js`

## Core Findings Before Audit

### 1. Standard ASCII minus appears to survive the SQL chain

The semantic SQL for orders and products uses regex patterns like `[^0-9.-]`, which preserve the standard `-` sign before casting to `numeric`.

This means values like `-123.45` should survive semantic parsing and downstream `SUM(...)` aggregation.

### 2. Unicode dash-style negatives are a real risk

Current parsing also strips `CHR(8212)` and `CHR(8211)` before regex cleanup. If upstream exports encode negative numbers as `—123` or `–123`, the sign can be removed before cast, turning a negative into a positive.

This risk exists in:

- `sql/semantic/orders_atomic.sql`
- `sql/semantic/products_atomic.sql`
- `backend/services/annual_cost_aggregate.py`

### 3. Raw B-class ingest is mostly symbol-preserving

Rows are stored into `raw_data` JSONB with very limited numeric normalization at ingest time. In practice, the main numeric interpretation happens later in semantic SQL, not during raw import.

This is good for forensics because the original exported text can still be inspected in `raw_data`.

### 4. Existing quality/consistency endpoints are not sufficient for formula audit

`backend/routers/data_quality.py` is useful for readiness/completeness checks, but not for proving metric correctness.

`backend/routers/data_consistency.py` still contains multiple TODO paths and legacy assumptions, so it should not be treated as the authoritative audit tool for PostgreSQL dashboard calculations.

## Audit Principles

Every audit item should be checked at four layers:

1. Raw source layer: `b_class`
2. Parsed semantic layer: `semantic`
3. Aggregated mart layer: `mart`
4. Frontend-facing API layer: `api` + backend service response

Do not jump directly to the API payload. If a number is wrong, locate the first layer where it diverges from expectation.

## Domain-To-Frontend Mapping

### Orders domain

Main chain:

- `b_class.fact_*_orders_daily|weekly|monthly`
- `semantic.fact_orders_atomic`
- `mart.shop_day_kpi`
- `mart.shop_week_kpi`
- `mart.shop_month_kpi`
- `mart.platform_month_kpi`
- `api.business_overview_kpi_module`
- `api.business_overview_comparison_module`
- `api.business_overview_shop_racing_module`
- `api.business_overview_operational_metrics_module`
- `api.annual_summary_*`

Core formulas:

- `gmv = SUM(paid_amount)`
- `order_count = COUNT(DISTINCT order_id)`
- `total_items = SUM(product_quantity)`
- `profit = SUM(profit)`

### Analytics / traffic domain

Main chain:

- `b_class.fact_*_analytics_daily|weekly|monthly`
- `semantic.fact_analytics_atomic`
- `mart.shop_day_kpi`
- `mart.shop_week_kpi`
- `mart.shop_month_kpi`
- `api.business_overview_*`

Core formulas:

- `visitor_count = SUM(visitor_count)`
- `page_views = SUM(page_views)`
- `conversion_rate = order_count / visitor_count`

### Products domain

Main chain:

- `b_class.fact_*_products_daily|weekly|monthly`
- `semantic.fact_products_atomic`
- `mart.product_day_kpi`
- `api.clearance_ranking_module`

Core formulas:

- `sales_amount = SUM(sales_amount)`
- `order_count = SUM(order_count)`
- `sales_volume = SUM(sales_volume)`
- `conversion_rate = SUM(order_count) / SUM(unique_visitors)`

### Inventory domain

Main chain:

- `b_class.fact_*_inventory_snapshot`
- `semantic.fact_inventory_snapshot`
- `mart.inventory_current`
- `mart.inventory_backlog_base`
- `api.business_overview_inventory_backlog_module`
- `api.clearance_ranking_module`

Core formulas:

- `daily_avg_sales = sold_units_30d / active_days_30d`
- `estimated_turnover_days = available_stock / daily_avg_sales`

### Annual summary / annual cost domain

Main chain:

- `mart.shop_month_kpi`
- `a_class.operating_costs`
- `mart.annual_summary_shop_month`
- `api.annual_summary_kpi_module`
- `api.annual_summary_trend_module`
- `api.annual_summary_platform_share_module`
- `api.annual_summary_by_shop_module`
- `backend/services/postgresql_dashboard_service.py:get_annual_summary_target_completion`
- `backend/services/annual_cost_aggregate.py`

Core formulas:

- `gross_margin = profit / gmv`
- `net_margin = (profit - total_cost) / gmv`
- `roi = (profit - total_cost) / total_cost`
- `target_completion = achieved_gmv / target_gmv`

## Module Audit Matrix

| Module | Main dependency path | Extra non-B-class dependency | Primary metrics to audit |
|---|---|---|---|
| `business_overview_kpi` | `orders -> shop_month_kpi -> platform_month_kpi -> api.business_overview_kpi_module` | none | `gmv`, `order_count`, `visitor_count`, `profit` |
| `business_overview_comparison` | `orders + analytics -> shop_day/week/month_kpi -> api.business_overview_comparison_module` | `a_class.sales_targets_a` | `sales_amount`, `sales_quantity`, `traffic`, `profit` |
| `business_overview_shop_racing` | `orders + analytics -> shop_day/week/month_kpi -> api.business_overview_shop_racing_module` | `a_class.target_breakdown`, `a_class.sales_targets` | `gmv`, `order_count`, `profit`, `achievement_rate` |
| `business_overview_traffic_ranking` | `analytics -> shop_day/week/month_kpi -> api.business_overview_traffic_ranking_module` | none | `visitor_count`, `page_views`, `conversion_rate` |
| `business_overview_inventory_backlog` | `inventory + orders -> inventory_current + inventory_backlog_base -> api.business_overview_inventory_backlog_module` | none | `available_stock`, `inventory_value`, `estimated_turnover_days` |
| `business_overview_operational_metrics` | `orders + analytics -> shop_month_kpi -> api.business_overview_operational_metrics_module` | `a_class.sales_targets_a`, `a_class.operating_costs` | `monthly_total_achieved`, `profit`, `estimated_expenses`, `operating_result` |
| `clearance_ranking` | `products + inventory -> product_day_kpi + inventory_backlog_base -> api.clearance_ranking_module` | none | `inventory_value`, `total_sales`, `estimated_turnover_days` |
| `annual_summary_kpi` | `shop_month_kpi -> annual_summary_shop_month -> api.annual_summary_kpi_module` | `a_class.operating_costs` | `gmv`, `total_cost`, `profit`, `gross_margin`, `net_margin`, `roi` |
| `annual_summary_trend` | `annual_summary_shop_month -> api.annual_summary_trend_module` | `a_class.operating_costs` | `gmv`, `total_cost`, `profit` |
| `annual_summary_platform_share` | `annual_summary_shop_month -> api.annual_summary_platform_share_module` | `a_class.operating_costs` | `gmv` |
| `annual_summary_by_shop` | `annual_summary_shop_month -> api.annual_summary_by_shop_module` | `a_class.operating_costs` | `gmv`, `total_cost`, `profit`, `roi` |
| `annual_summary_target_completion` | `annual_summary_kpi + sales_targets_a` | `a_class.sales_targets_a` | `target_gmv`, `achieved_gmv`, `achievement_rate_gmv` |
| `annual_cost_aggregate` | raw monthly order tables parsed in service | `a_class.operating_costs` | `gmv`, `total_cost_a`, `total_cost_b`, `gross_margin`, `net_margin`, `roi` |

## Standard Audit Workflow

### Step 1. Confirm raw sign preservation

For the target platform/month/shop, inspect the literal raw text first.

```sql
SELECT
  COALESCE(raw_data->>'利润', raw_data->>'profit', raw_data->>'净利润') AS profit_text,
  COUNT(*) AS row_count
FROM b_class.fact_shopee_orders_monthly
WHERE period_start_date >= :period_start
  AND period_start_date < :period_end
GROUP BY 1
ORDER BY row_count DESC;
```

Then explicitly count dash styles:

```sql
SELECT
  COUNT(*) FILTER (
    WHERE COALESCE(raw_data->>'利润', raw_data->>'profit', raw_data->>'净利润') LIKE '%-%'
  ) AS ascii_minus_rows,
  COUNT(*) FILTER (
    WHERE COALESCE(raw_data->>'利润', raw_data->>'profit', raw_data->>'净利润') LIKE '%–%'
  ) AS en_dash_rows,
  COUNT(*) FILTER (
    WHERE COALESCE(raw_data->>'利润', raw_data->>'profit', raw_data->>'净利润') LIKE '%—%'
  ) AS em_dash_rows
FROM b_class.fact_shopee_orders_monthly
WHERE period_start_date >= :period_start
  AND period_start_date < :period_end;
```

Interpretation:

- `ascii_minus_rows > 0` is expected and usually safe.
- `en_dash_rows > 0` or `em_dash_rows > 0` means the current parser may flip signs.

### Step 2. Verify semantic parsing

Confirm that negative profits still exist after semantic parsing.

```sql
SELECT
  platform_code,
  shop_id,
  COUNT(*) FILTER (WHERE profit < 0) AS negative_profit_rows,
  SUM(profit) AS total_profit,
  MIN(profit) AS min_profit,
  MAX(profit) AS max_profit
FROM semantic.fact_orders_atomic
WHERE metric_date >= :period_start
  AND metric_date < :period_end
GROUP BY 1, 2
ORDER BY total_profit ASC;
```

If raw layer clearly contains negatives but semantic layer shows none, the parsing layer is the first broken layer.

### Step 3. Verify mart aggregation

For daily and monthly audit:

```sql
SELECT
  period_date,
  platform_code,
  shop_id,
  gmv,
  order_count,
  total_items,
  profit
FROM mart.shop_day_kpi
WHERE platform_code = :platform_code
  AND shop_id = :shop_id
  AND period_date >= :period_start
  AND period_date < :period_end
ORDER BY period_date;
```

```sql
SELECT
  period_month,
  platform_code,
  shop_id,
  gmv,
  order_count,
  visitor_count,
  profit
FROM mart.shop_month_kpi
WHERE platform_code = :platform_code
  AND shop_id = :shop_id
ORDER BY period_month;
```

Check that:

- `gmv` matches `SUM(paid_amount)` from semantic orders
- `profit` matches `SUM(profit)` from semantic orders
- `order_count` matches `COUNT(DISTINCT order_id)` semantics

### Step 4. Verify API module output

Inspect the exact API-facing view before going to HTTP:

```sql
SELECT *
FROM api.business_overview_operational_metrics_module
WHERE platform_code = :platform_code
  AND shop_id = :shop_id
ORDER BY period_month DESC;
```

If SQL is correct here but frontend display is wrong, the bug is in backend response shaping or frontend rendering, not the data calculation.

### Step 5. Verify backend response

Use the actual route:

```bash
python scripts/smoke_postgresql_dashboard_routes.py --base-url http://localhost:8001
```

This only proves route health. It does not replace SQL-layer reconciliation.

## Per-Metric Reconciliation Pack

### A. Profit audit

Use this sequence:

1. raw `profit_text`
2. `semantic.fact_orders_atomic.profit`
3. `mart.shop_day_kpi.profit`
4. `mart.shop_month_kpi.profit`
5. target API module field

Reference SQL:

```sql
WITH semantic_profit AS (
  SELECT
    date_trunc('month', metric_date)::date AS period_month,
    platform_code,
    shop_id,
    SUM(profit) AS semantic_profit
  FROM semantic.fact_orders_atomic
  GROUP BY 1, 2, 3
)
SELECT
  s.period_month,
  s.platform_code,
  s.shop_id,
  s.semantic_profit,
  m.profit AS mart_profit,
  (m.profit - s.semantic_profit) AS diff
FROM semantic_profit s
LEFT JOIN mart.shop_month_kpi m
  ON m.period_month = s.period_month
 AND m.platform_code = s.platform_code
 AND COALESCE(m.shop_id, '') = COALESCE(s.shop_id, '')
ORDER BY ABS(COALESCE(m.profit, 0) - COALESCE(s.semantic_profit, 0)) DESC;
```

Expected:

- `diff = 0` or only rounding-level differences.

### B. GMV audit

```sql
WITH semantic_gmv AS (
  SELECT
    date_trunc('month', metric_date)::date AS period_month,
    platform_code,
    shop_id,
    SUM(paid_amount) AS semantic_gmv
  FROM semantic.fact_orders_atomic
  GROUP BY 1, 2, 3
)
SELECT
  s.period_month,
  s.platform_code,
  s.shop_id,
  s.semantic_gmv,
  m.gmv AS mart_gmv,
  (m.gmv - s.semantic_gmv) AS diff
FROM semantic_gmv s
LEFT JOIN mart.shop_month_kpi m
  ON m.period_month = s.period_month
 AND m.platform_code = s.platform_code
 AND COALESCE(m.shop_id, '') = COALESCE(s.shop_id, '')
ORDER BY ABS(COALESCE(m.gmv, 0) - COALESCE(s.semantic_gmv, 0)) DESC;
```

### C. Order-count audit

```sql
WITH semantic_orders AS (
  SELECT
    date_trunc('month', metric_date)::date AS period_month,
    platform_code,
    shop_id,
    COUNT(DISTINCT order_id) AS semantic_order_count
  FROM semantic.fact_orders_atomic
  GROUP BY 1, 2, 3
)
SELECT
  s.period_month,
  s.platform_code,
  s.shop_id,
  s.semantic_order_count,
  m.order_count AS mart_order_count,
  (m.order_count - s.semantic_order_count) AS diff
FROM semantic_orders s
LEFT JOIN mart.shop_month_kpi m
  ON m.period_month = s.period_month
 AND m.platform_code = s.platform_code
 AND COALESCE(m.shop_id, '') = COALESCE(s.shop_id, '')
ORDER BY ABS(COALESCE(m.order_count, 0) - COALESCE(s.semantic_order_count, 0)) DESC;
```

## Module-Specific Audit Notes

### `business_overview_kpi`

Audit path:

- `mart.platform_month_kpi`
- `api.business_overview_kpi_module`
- backend reducer should not materially alter SQL totals

Check:

- platform totals equal the sum of `mart.shop_month_kpi` by platform/month

### `business_overview_comparison`

Audit path:

- `mart.shop_day_kpi` / `shop_week_kpi` / `shop_month_kpi`
- `api.business_overview_comparison_module`
- `reduce_business_overview_comparison_rows()`

Check:

- monthly target values come from `a_class.sales_targets_a`
- `change` is backend-computed, not SQL-computed
- if the SQL rows are right but the returned comparison block is wrong, inspect service reducer logic

### `business_overview_shop_racing`

Audit path:

- `api.business_overview_shop_racing_module`
- `a_class.target_breakdown`
- service ranking logic

Check:

- `achievement_rate` should reconcile to `gmv / target_amount`
- target source changes by granularity logic in the SQL view

### `business_overview_traffic_ranking`

Audit path:

- `api.business_overview_traffic_ranking_module`
- backend ranking by `visitor_count` or `page_views`

Check:

- SQL numbers first
- then backend sort dimension

### `business_overview_inventory_backlog`

Audit path:

- `mart.inventory_current`
- `mart.inventory_backlog_base`
- `api.business_overview_inventory_backlog_module`

Check:

- `estimated_turnover_days` uses the trailing 30-day order-derived volume
- watch for shops/products with zero sales but positive stock, which intentionally map to `9999`

### `business_overview_operational_metrics`

Audit path:

- `mart.shop_month_kpi`
- `a_class.sales_targets_a`
- `a_class.operating_costs`
- `api.business_overview_operational_metrics_module`

Check:

- `estimated_gross_profit = m.profit`
- `estimated_expenses = rent + salary + utilities + other_costs`
- `operating_result = profit - estimated_expenses`

### `clearance_ranking`

Audit path:

- `mart.product_day_kpi`
- `mart.inventory_backlog_base`
- `api.clearance_ranking_module`

Check:

- product sales and inventory join on platform/shop/sku
- missing SKU normalization will show up here as low sales with large inventory

### `annual_summary_*`

Audit path:

- `mart.annual_summary_shop_month`
- annual summary API views

Check:

- `gross_margin = profit / gmv`
- `net_margin = (profit - total_cost) / gmv`
- `roi = (profit - total_cost) / total_cost`

### `annual_summary_target_completion`

Audit path:

- `a_class.sales_targets_a`
- `api.annual_summary_kpi_module`
- backend `get_annual_summary_target_completion()`

Check:

- target is queried from `sales_targets_a`
- achieved GMV comes from the annual summary KPI service, not a separate SQL object

### `annual_cost_aggregate`

Audit path:

- `a_class.operating_costs`
- raw monthly B-class order tables
- service-only calculation in `backend/services/annual_cost_aggregate.py`

This service does not fully reuse the `semantic / mart / api` path. It reparses `raw_data` directly from monthly order tables. That makes it high-risk and high-priority for audit.

Primary check:

```sql
SELECT
  date_trunc('month', metric_date)::date AS period_month,
  platform_code,
  shop_id,
  SUM(paid_amount) AS semantic_gmv
FROM semantic.fact_orders_atomic
WHERE granularity IN ('monthly', 'daily')
GROUP BY 1, 2, 3
ORDER BY period_month, platform_code, shop_id;
```

Then compare against the service result for the same period and shop key.

## Exception Rules

Treat any of the following as audit failures:

- raw layer contains negative values but semantic layer has none
- semantic monthly `SUM(profit)` does not equal mart monthly `profit`
- mart values do not match corresponding `api.*_module` rows
- backend reducer changes SQL totals unexpectedly
- `annual_cost_aggregate` disagrees with semantic/mart totals for the same period
- Unicode dash negatives exist in raw data for any audited source file

## Recommended Audit Order

1. Pick one platform and one month with known returns/refunds.
2. Run raw sign-preservation SQL.
3. Reconcile semantic vs mart for `profit`, `gmv`, `order_count`.
4. Reconcile `business_overview_operational_metrics`.
5. Reconcile annual summary views.
6. Reconcile `annual_cost_aggregate`.
7. Only then expand to other shops/platforms.

## Audit Record Template

Use this record format for each audited scope:

```markdown
### Audit Record

- Scope: `platform=...`, `shop_id=...`, `period=...`
- Module: `...`
- Raw negatives present: yes/no
- Unicode dash negatives present: yes/no
- Semantic vs mart diff:
- Mart vs api diff:
- Backend response diff:
- Status: pass/fail
- Notes:
```

## Immediate Follow-Up Recommendation

The first live audit should focus on one month where:

- returns/refunds definitely occurred
- profit is known to be zero or negative for at least some orders
- both dashboard and annual-cost views are actively used

That sample will tell us quickly whether the minus-sign risk is theoretical or already affecting production numbers.
