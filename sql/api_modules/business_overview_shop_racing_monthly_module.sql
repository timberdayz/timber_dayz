CREATE SCHEMA IF NOT EXISTS api;

DROP VIEW IF EXISTS api.business_overview_shop_racing_monthly_module;
DROP MATERIALIZED VIEW IF EXISTS api.business_overview_shop_racing_monthly_module;

CREATE MATERIALIZED VIEW api.business_overview_shop_racing_monthly_module AS
WITH target_summary AS (
    SELECT
        tb.platform_code,
        tb.shop_id,
        CASE
            WHEN SUM(CASE WHEN tb.breakdown_type = 'shop' THEN tb.target_amount ELSE 0 END) > 0
            THEN SUM(CASE WHEN tb.breakdown_type = 'shop' THEN tb.target_amount ELSE 0 END)::numeric
            ELSE SUM(CASE WHEN tb.breakdown_type = 'shop_time' THEN tb.target_amount ELSE 0 END)::numeric
        END AS target_amount
    FROM a_class.target_breakdown tb
    INNER JOIN a_class.sales_targets st
      ON st.id = tb.target_id
     AND st.status = 'active'
    WHERE tb.breakdown_type IN ('shop', 'shop_time')
    GROUP BY tb.platform_code, tb.shop_id
),
orders_agg AS (
    SELECT
        metric_date AS period_key,
        platform_code,
        shop_id,
        SUM(paid_amount) AS gmv,
        CASE WHEN COUNT(*) > 0 THEN COUNT(DISTINCT order_id)::numeric ELSE NULL END AS order_count,
        SUM(product_quantity) AS total_items,
        SUM(profit) AS profit
    FROM semantic.fact_orders_monthly_atomic
    GROUP BY metric_date, platform_code, shop_id
)
SELECT
    'monthly'::varchar AS granularity,
    o.period_key,
    o.platform_code,
    o.shop_id,
    o.gmv,
    o.order_count,
    CASE
        WHEN o.gmv IS NOT NULL AND o.order_count > 0 THEN ROUND(o.gmv::numeric / o.order_count, 2)
        WHEN o.gmv IS NOT NULL AND o.order_count = 0 AND o.gmv = 0 THEN 0
        ELSE NULL
    END AS avg_order_value,
    CASE
        WHEN o.total_items IS NOT NULL AND o.order_count > 0 THEN ROUND(o.total_items::numeric / o.order_count, 2)
        WHEN o.total_items IS NOT NULL AND o.order_count = 0 AND o.total_items = 0 THEN 0
        ELSE NULL
    END AS attach_rate,
    o.profit,
    COALESCE(t.target_amount, 0) AS target_amount,
    CASE
        WHEN COALESCE(t.target_amount, 0) > 0 THEN ROUND(o.gmv::numeric * 100.0 / t.target_amount, 2)
        ELSE 0::numeric
    END AS achievement_rate
FROM orders_agg o
LEFT JOIN target_summary t
  ON t.platform_code = o.platform_code
 AND COALESCE(t.shop_id, '') = COALESCE(o.shop_id, '');

CREATE INDEX IF NOT EXISTS ix_business_overview_shop_racing_monthly_period
ON api.business_overview_shop_racing_monthly_module (period_key, platform_code, shop_id);
