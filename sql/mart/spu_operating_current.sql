CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.spu_operating_current AS
WITH active_bindings AS (
    SELECT spu, sku_id
    FROM core.bridge_spu_sku
    WHERE binding_status = 'active'
      AND effective_to IS NULL
),
inventory AS (
    SELECT
        b.spu,
        COUNT(DISTINCT b.sku_id) AS sku_count,
        SUM(COALESCE(a.current_qty, 0)) AS total_qty,
        SUM(COALESCE(a.inventory_value, 0)) AS inventory_value_rmb,
        SUM(CASE WHEN a.bucket = '31-60' THEN COALESCE(a.current_qty, 0) ELSE 0 END) AS qty_31_60,
        SUM(CASE WHEN a.bucket = '61-90' THEN COALESCE(a.current_qty, 0) ELSE 0 END) AS qty_61_90,
        SUM(CASE WHEN a.bucket = '91-180' THEN COALESCE(a.current_qty, 0) ELSE 0 END) AS qty_91_180,
        SUM(CASE WHEN a.bucket = '180+' THEN COALESCE(a.current_qty, 0) ELSE 0 END) AS qty_180_plus,
        MAX(a.age_days) AS oldest_age_days,
        MAX(a.snapshot_date) AS snapshot_date
    FROM active_bindings b
    JOIN core.dim_erp_sku s ON s.sku_id = b.sku_id
    LEFT JOIN mart.inventory_age_current a ON a.sku_key = s.sku_key
    GROUP BY b.spu
),
latest_estimates AS (
    SELECT DISTINCT ON (e.sku_id)
        e.sku_id,
        e.selling_price,
        e.estimated_contribution_profit,
        e.estimated_margin_rate,
        e.estimate_as_of,
        e.cost_completeness,
        e.confidence_level
    FROM finance.sku_profit_estimates e
    WHERE e.scenario = 'base'
    ORDER BY e.sku_id, e.estimate_as_of DESC
),
profit AS (
    SELECT
        b.spu,
        SUM(COALESCE(e.estimated_contribution_profit, 0)) AS estimated_profit,
        SUM(COALESCE(e.selling_price, 0)) AS estimated_revenue,
        MAX(e.estimate_as_of) AS calculated_at
    FROM active_bindings b
    LEFT JOIN latest_estimates e ON e.sku_id = b.sku_id
    GROUP BY b.spu
)
SELECT
    d.spu,
    d.spu_name,
    d.category_l1,
    d.category_l2,
    d.biz_status,
    d.owner_user_id,
    COALESCE(i.sku_count, 0) AS sku_count,
    COALESCE(i.total_qty, 0) AS total_qty,
    COALESCE(i.inventory_value_rmb, 0) AS inventory_value_rmb,
    COALESCE(i.qty_31_60, 0) AS qty_31_60,
    COALESCE(i.qty_61_90, 0) AS qty_61_90,
    COALESCE(i.qty_91_180, 0) AS qty_91_180,
    COALESCE(i.qty_180_plus, 0) AS qty_180_plus,
    COALESCE(i.oldest_age_days, 0) AS oldest_age_days,
    COALESCE(p.estimated_profit, 0) AS estimated_profit,
    CASE WHEN COALESCE(p.estimated_revenue, 0) > 0 THEN p.estimated_profit / p.estimated_revenue ELSE NULL END AS estimated_margin_rate,
    i.snapshot_date,
    p.calculated_at
FROM core.dim_spu d
LEFT JOIN inventory i ON i.spu = d.spu
LEFT JOIN profit p ON p.spu = d.spu
WHERE d.active = true;
