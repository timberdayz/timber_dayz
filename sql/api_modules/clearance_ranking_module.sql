CREATE SCHEMA IF NOT EXISTS api;

-- The previous view exposed a different leading-column contract. PostgreSQL
-- cannot rename view columns through CREATE OR REPLACE VIEW, so rebuild it.
DROP VIEW IF EXISTS api.clearance_ranking_module;

CREATE OR REPLACE VIEW api.clearance_ranking_module AS
-- The previous implementation selected mart.inventory_backlog_base rows.
-- This view keeps compatibility fields while exposing monthly shop rankings.
WITH order_months AS (
    SELECT
        date_trunc('month', o.metric_date)::date AS ranking_month,
        o.platform_code,
        COALESCE(NULLIF(BTRIM(to_jsonb(o)->>'sku_id'), ''), NULLIF(BTRIM(o.platform_sku), ''),
                 NULLIF(BTRIM(o.product_sku), ''), NULLIF(BTRIM(to_jsonb(o)->>'product_id'), '')) AS sku_key,
        o.shop_id,
        COALESCE(
            CASE WHEN (to_jsonb(o)->>'paid_amount') ~ '^-?[0-9]+(\\.[0-9]+)?$' THEN (to_jsonb(o)->>'paid_amount')::numeric END,
            CASE WHEN (to_jsonb(o)->>'sales_amount') ~ '^-?[0-9]+(\\.[0-9]+)?$' THEN (to_jsonb(o)->>'sales_amount')::numeric END,
            0
        ) AS sales_amount,
        COALESCE(o.product_quantity, 0)::numeric AS sales_quantity
    FROM semantic.fact_orders_atomic o
    WHERE o.metric_date IS NOT NULL
),
stagnant_before_month AS (
    SELECT DISTINCT ON (h.platform_code, h.sku_key, m.ranking_month)
        m.ranking_month,
        h.platform_code,
        h.sku_key,
        GREATEST(COALESCE(h.estimated_stagnant_days, 0), COALESCE(h.estimated_turnover_days, 0)) AS age_days,
        h.inventory_value
    FROM order_months m
    JOIN LATERAL (
        SELECT
            b.platform_code,
            COALESCE(NULLIF(BTRIM(b.platform_sku), ''), NULLIF(BTRIM(b.product_sku), ''), NULLIF(BTRIM(b.product_id), '')) AS sku_key,
            b.snapshot_date,
            b.estimated_stagnant_days,
            b.estimated_turnover_days,
            GREATEST(COALESCE(b.estimated_stagnant_days, 0), COALESCE(b.estimated_turnover_days, 0)) AS age_days,
            b.inventory_value
        FROM mart.inventory_backlog_base b
        WHERE b.snapshot_date < m.ranking_month
           OR NOT EXISTS (
                SELECT 1
                FROM mart.inventory_backlog_base prior
                WHERE prior.platform_code = b.platform_code
                  AND COALESCE(NULLIF(BTRIM(prior.platform_sku), ''), NULLIF(BTRIM(prior.product_sku), ''), NULLIF(BTRIM(prior.product_id), '')) =
                      COALESCE(NULLIF(BTRIM(b.platform_sku), ''), NULLIF(BTRIM(b.product_sku), ''), NULLIF(BTRIM(b.product_id), ''))
                  AND prior.snapshot_date < m.ranking_month
           )
        ORDER BY (b.snapshot_date < m.ranking_month) DESC, b.snapshot_date DESC
        LIMIT 1
    ) h
      ON h.platform_code = m.platform_code
     AND h.sku_key = m.sku_key
     AND h.age_days >= 30
    ORDER BY h.platform_code, h.sku_key, m.ranking_month, h.snapshot_date DESC
),
shop_month AS (
    SELECT
        o.ranking_month,
        o.platform_code,
        o.shop_id,
        COALESCE(o.shop_id, 'unknown') AS shop_name,
        SUM(o.sales_amount) AS clearance_amount,
        SUM(o.sales_quantity) AS clearance_quantity,
        COUNT(DISTINCT o.sku_key) AS stagnant_sku_count,
        MAX(st.age_days) AS max_stagnant_age_days
    FROM order_months o
    JOIN stagnant_before_month st
      ON st.ranking_month = o.ranking_month
     AND st.platform_code = o.platform_code
     AND st.sku_key = o.sku_key
    GROUP BY o.ranking_month, o.platform_code, o.shop_id
)
SELECT
    ranking_month,
    platform_code,
    shop_id,
    shop_name,
    clearance_amount,
    clearance_quantity,
    stagnant_sku_count,
    max_stagnant_age_days,
    max_stagnant_age_days AS estimated_turnover_days,
    NULL::numeric AS daily_avg_sales,
    stagnant_sku_count AS stagnant_snapshot_count,
    max_stagnant_age_days AS estimated_stagnant_days,
    CASE
        WHEN max_stagnant_age_days >= 180 THEN 'high'
        WHEN max_stagnant_age_days >= 90 THEN 'medium'
        ELSE 'low'
    END AS risk_level,
    clearance_amount AS inventory_value,
    NULL::text AS platform_sku,
    NULL::text AS product_sku,
    NULL::text AS product_name,
    clearance_amount AS clearance_priority_score,
    ROW_NUMBER() OVER (
        PARTITION BY ranking_month
        ORDER BY clearance_amount DESC, clearance_quantity DESC, shop_name ASC
    ) AS rank,
    clearance_amount AS total_sales,
    clearance_quantity AS total_orders
FROM shop_month;
