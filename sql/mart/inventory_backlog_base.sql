CREATE SCHEMA IF NOT EXISTS mart;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_matviews
        WHERE schemaname = 'mart'
          AND matviewname = 'inventory_backlog_base_mv'
    ) THEN
        EXECUTE $mv$
CREATE MATERIALIZED VIEW mart.inventory_backlog_base_mv AS
-- Current backlog calculation runs on company-level inventory scope.
-- shop_id remains a reserved interface field and is not part of the current
-- latest snapshot, sales join, or risk aggregation key.
WITH latest_snapshot AS (
    SELECT
        snapshot_date,
        platform_code,
        NULL::text AS shop_id,
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
        platform_sku,
        product_sku,
        COALESCE(SUM(product_quantity), 0) AS sold_units_30d,
        COUNT(DISTINCT metric_date::date) AS active_days_30d
    FROM semantic.fact_orders_atomic
    WHERE metric_date::date >= CURRENT_DATE - INTERVAL '30 days'
      AND metric_date::date <= CURRENT_DATE
    GROUP BY platform_code, platform_sku, product_sku
),
joined_backlog AS (
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
        COALESCE(s.sold_units_30d, 0) AS sold_units_30d,
        COALESCE(s.active_days_30d, 0) AS active_days_30d,
        COALESCE(c.stock_delta, 0) AS stock_delta,
        COALESCE(c.inventory_value_delta, 0) AS inventory_value_delta,
        COALESCE(c.is_stagnant, FALSE) AS is_stagnant,
        COALESCE(c.snapshot_gap_days, 0) AS snapshot_gap_days,
        COALESCE(c.estimated_stagnant_days, 0) AS estimated_stagnant_days,
        COALESCE(c.stagnant_snapshot_count, 0) AS stagnant_snapshot_count
    FROM latest_snapshot i
    LEFT JOIN sales_30d s
        ON i.platform_code = s.platform_code
       AND COALESCE(i.platform_sku, '') = COALESCE(s.platform_sku, '')
       AND COALESCE(i.product_sku, '') = COALESCE(s.product_sku, '')
    LEFT JOIN snapshot_change c
        ON i.platform_code = c.platform_code
       AND COALESCE(i.platform_sku, '') = COALESCE(c.platform_sku, '')
       AND COALESCE(i.product_sku, '') = COALESCE(c.product_sku, '')
       AND COALESCE(i.warehouse_name, '') = COALESCE(c.warehouse_name, '')
),
turnover_enriched AS (
    SELECT
        base.snapshot_date,
        base.platform_code,
        base.shop_id,
        base.product_id,
        base.product_name,
        base.platform_sku,
        base.product_sku,
        base.warehouse_name,
        base.available_stock,
        base.on_hand_stock,
        base.inventory_value,
        COALESCE(
            ROUND(
                base.sold_units_30d::numeric / NULLIF(base.active_days_30d, 0),
                2
            ),
            0
        ) AS daily_avg_sales,
        CASE
            WHEN base.sold_units_30d > 0 AND base.active_days_30d > 0
            THEN ROUND(
                COALESCE(base.available_stock, 0)::numeric /
                NULLIF(base.sold_units_30d::numeric / base.active_days_30d, 0),
                0
            )
            WHEN COALESCE(base.available_stock, 0) > 0
            THEN 9999
            ELSE 0
        END AS estimated_turnover_days,
        base.stock_delta,
        base.inventory_value_delta,
        base.is_stagnant,
        base.snapshot_gap_days,
        base.estimated_stagnant_days,
        base.stagnant_snapshot_count
    FROM joined_backlog base
)
SELECT
    base.snapshot_date,
    base.platform_code,
    base.shop_id,
    base.product_id,
    base.product_name,
    base.platform_sku,
    base.product_sku,
    base.warehouse_name,
    base.available_stock,
    base.on_hand_stock,
    base.inventory_value,
    base.daily_avg_sales,
    base.estimated_turnover_days,
    base.stock_delta,
    base.inventory_value_delta,
    base.is_stagnant,
    base.snapshot_gap_days,
    base.estimated_stagnant_days,
    base.stagnant_snapshot_count,
    CASE
        WHEN base.estimated_turnover_days >= 60
        OR base.stagnant_snapshot_count >= 3
        THEN 'high'
        WHEN base.estimated_turnover_days >= 30
        OR base.stagnant_snapshot_count >= 2
        THEN 'medium'
        ELSE 'low'
    END AS risk_level,
    (
        COALESCE(base.inventory_value, 0) * 0.5
        + base.estimated_stagnant_days * 10
        + base.estimated_turnover_days * 2
    ) AS clearance_priority_score
FROM turnover_enriched base;
$mv$;
    END IF;
END$$;

REFRESH MATERIALIZED VIEW mart.inventory_backlog_base_mv;

CREATE INDEX IF NOT EXISTS ix_inventory_backlog_base_mv_snapshot_platform
ON mart.inventory_backlog_base_mv (snapshot_date, platform_code);

CREATE INDEX IF NOT EXISTS ix_inventory_backlog_base_mv_snapshot_turnover
ON mart.inventory_backlog_base_mv (snapshot_date, estimated_turnover_days);

CREATE INDEX IF NOT EXISTS ix_inventory_backlog_base_mv_snapshot_clearance_order
ON mart.inventory_backlog_base_mv (
    snapshot_date,
    clearance_priority_score DESC,
    inventory_value DESC,
    estimated_turnover_days DESC
);

CREATE OR REPLACE VIEW mart.inventory_backlog_base AS
SELECT *
FROM mart.inventory_backlog_base_mv;
