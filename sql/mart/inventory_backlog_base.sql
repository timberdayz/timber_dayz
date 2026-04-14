CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.inventory_backlog_base AS
WITH latest_snapshot AS (
    SELECT
        snapshot_date,
        platform_code,
        shop_id,
        product_id,
        product_name,
        platform_sku,
        product_sku,
        warehouse_name,
        available_stock,
        on_hand_stock,
        inventory_value
    FROM mart.inventory_snapshot_latest
),
snapshot_change AS (
    SELECT
        snapshot_date,
        platform_code,
        shop_id,
        product_id,
        product_name,
        platform_sku,
        product_sku,
        warehouse_name,
        stock_delta,
        inventory_value_delta,
        is_stagnant,
        snapshot_gap_days,
        estimated_stagnant_days,
        stagnant_snapshot_count
    FROM mart.inventory_snapshot_change
),
sales_30d AS (
    SELECT
        platform_code,
        shop_id,
        platform_sku,
        product_sku,
        COALESCE(SUM(product_quantity), 0) AS sold_units_30d,
        COUNT(DISTINCT metric_date::date) AS active_days_30d
    FROM semantic.fact_orders_atomic
    WHERE metric_date::date >= CURRENT_DATE - INTERVAL '30 days'
      AND metric_date::date <= CURRENT_DATE
    GROUP BY platform_code, shop_id, platform_sku, product_sku
)
SELECT
    i.snapshot_date,
    i.platform_code,
    i.shop_id,
    i.product_id,
    i.product_name,
    i.platform_sku,
    i.product_sku,
    i.warehouse_name,
    i.available_stock,
    i.on_hand_stock,
    i.inventory_value,
    COALESCE(
        ROUND(
            COALESCE(s.sold_units_30d, 0)::numeric / NULLIF(COALESCE(s.active_days_30d, 0), 0),
            2
        ),
        0
    ) AS daily_avg_sales,
    CASE
        WHEN COALESCE(s.sold_units_30d, 0) > 0 AND COALESCE(s.active_days_30d, 0) > 0
        THEN ROUND(
            COALESCE(i.available_stock, 0)::numeric /
            NULLIF(COALESCE(s.sold_units_30d, 0)::numeric / s.active_days_30d, 0),
            0
        )
        WHEN COALESCE(i.available_stock, 0) > 0
        THEN 9999
        ELSE 0
    END AS estimated_turnover_days,
    COALESCE(c.stock_delta, 0) AS stock_delta,
    COALESCE(c.inventory_value_delta, 0) AS inventory_value_delta,
    COALESCE(c.is_stagnant, FALSE) AS is_stagnant,
    COALESCE(c.snapshot_gap_days, 0) AS snapshot_gap_days,
    COALESCE(c.estimated_stagnant_days, 0) AS estimated_stagnant_days,
    COALESCE(c.stagnant_snapshot_count, 0) AS stagnant_snapshot_count,
    CASE
        WHEN (
            CASE
                WHEN COALESCE(s.sold_units_30d, 0) > 0 AND COALESCE(s.active_days_30d, 0) > 0
                THEN ROUND(
                    COALESCE(i.available_stock, 0)::numeric /
                    NULLIF(COALESCE(s.sold_units_30d, 0)::numeric / s.active_days_30d, 0),
                    0
                )
                WHEN COALESCE(i.available_stock, 0) > 0
                THEN 9999
                ELSE 0
            END
        ) >= 60
        OR COALESCE(c.stagnant_snapshot_count, 0) >= 3
        THEN 'high'
        WHEN (
            CASE
                WHEN COALESCE(s.sold_units_30d, 0) > 0 AND COALESCE(s.active_days_30d, 0) > 0
                THEN ROUND(
                    COALESCE(i.available_stock, 0)::numeric /
                    NULLIF(COALESCE(s.sold_units_30d, 0)::numeric / s.active_days_30d, 0),
                    0
                )
                WHEN COALESCE(i.available_stock, 0) > 0
                THEN 9999
                ELSE 0
            END
        ) >= 30
        OR COALESCE(c.stagnant_snapshot_count, 0) >= 2
        THEN 'medium'
        ELSE 'low'
    END AS risk_level,
    (
        COALESCE(i.inventory_value, 0) * 0.5
        + COALESCE(c.estimated_stagnant_days, 0) * 10
        + (
            CASE
                WHEN COALESCE(s.sold_units_30d, 0) > 0 AND COALESCE(s.active_days_30d, 0) > 0
                THEN ROUND(
                    COALESCE(i.available_stock, 0)::numeric /
                    NULLIF(COALESCE(s.sold_units_30d, 0)::numeric / s.active_days_30d, 0),
                    0
                )
                WHEN COALESCE(i.available_stock, 0) > 0
                THEN 9999
                ELSE 0
            END
        ) * 2
    ) AS clearance_priority_score
FROM latest_snapshot i
LEFT JOIN sales_30d s
    ON i.platform_code = s.platform_code
   AND COALESCE(i.shop_id, '') = COALESCE(s.shop_id, '')
   AND COALESCE(i.platform_sku, '') = COALESCE(s.platform_sku, '')
   AND COALESCE(i.product_sku, '') = COALESCE(s.product_sku, '')
LEFT JOIN snapshot_change c
    ON i.platform_code = c.platform_code
   AND COALESCE(i.shop_id, '') = COALESCE(c.shop_id, '')
   AND COALESCE(i.platform_sku, '') = COALESCE(c.platform_sku, '')
   AND COALESCE(i.product_sku, '') = COALESCE(c.product_sku, '')
   AND COALESCE(i.warehouse_name, '') = COALESCE(c.warehouse_name, '');
