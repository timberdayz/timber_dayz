CREATE SCHEMA IF NOT EXISTS api;

-- Current launch contract:
-- - a_class.sales_targets_a: "年月", "店铺ID", "目标销售额"
-- - a_class.operating_costs: "年月", "店铺ID", "成本合计" (or rent-like Chinese columns)
CREATE OR REPLACE VIEW api.business_overview_operational_metrics_module AS
WITH base_month_kpi AS (
    SELECT
        m.period_month,
        m.platform_code,
        m.shop_id,
        m.gmv,
        m.order_count,
        m.profit,
        CASE
            WHEN CURRENT_DATE < m.period_month THEN m.period_month
            WHEN CURRENT_DATE > (m.period_month + INTERVAL '1 month - 1 day')::date THEN (m.period_month + INTERVAL '1 month - 1 day')::date
            ELSE CURRENT_DATE
        END AS anchor_date,
        CASE
            WHEN CURRENT_DATE < m.period_month THEN 0::numeric
            WHEN CURRENT_DATE > (m.period_month + INTERVAL '1 month - 1 day')::date THEN 100::numeric
            ELSE ROUND(
                ((CURRENT_DATE - m.period_month + 1)::numeric * 100.0) /
                NULLIF(((m.period_month + INTERVAL '1 month - 1 day')::date - m.period_month + 1)::numeric, 0),
                2
            )
        END AS time_progress_pct
    FROM mart.shop_month_kpi m
),
monthly_targets AS (
    SELECT
        to_date("年月" || '-01', 'YYYY-MM-DD') AS period_month,
        LOWER(TRIM(COALESCE(platform_code, ''))) AS platform_code,
        "店铺ID" AS shop_id,
        SUM("目标销售额") AS monthly_target
    FROM a_class.sales_targets_a
    GROUP BY
        to_date("年月" || '-01', 'YYYY-MM-DD'),
        LOWER(TRIM(COALESCE(platform_code, ''))),
        "店铺ID"
),
monthly_costs AS (
    SELECT
        COALESCE(o.period_month, l.period_month) AS period_month,
        COALESCE(o.platform_code, l.platform_code) AS platform_code,
        COALESCE(o.shop_id, l.shop_id) AS shop_id,
        COALESCE(o.other_operating_cost, 0) AS other_operating_cost,
        COALESCE(l.pre_commission_labor_cost, 0) AS pre_commission_labor_cost,
        COALESCE(l.performance_labor_cost, 0) AS performance_labor_cost,
        COALESCE(l.commission_labor_cost, 0) AS commission_labor_cost,
        COALESCE(l.total_labor_cost, 0) AS total_labor_cost,
        COALESCE(o.other_operating_cost, 0) + COALESCE(l.total_labor_cost, 0) AS estimated_expenses,
        COALESCE(l.cost_status, 'legacy') AS cost_status
    FROM semantic.shop_month_other_operating_cost o
    FULL OUTER JOIN mart.shop_month_labor_cost l
        ON o.period_month = l.period_month
       AND o.platform_code = l.platform_code
       AND COALESCE(o.shop_id, '') = COALESCE(l.shop_id, '')
)
SELECT
    m.period_month,
    m.platform_code,
    m.shop_id,
    t.monthly_target AS monthly_target,
    m.gmv AS monthly_total_achieved,
    ds.gmv AS today_sales,
    CASE
        WHEN t.monthly_target IS NULL OR m.gmv IS NULL THEN NULL
        WHEN t.monthly_target > 0 THEN ROUND(m.gmv::numeric * 100.0 / t.monthly_target, 2)
        WHEN t.monthly_target = 0 AND m.gmv = 0 THEN 0
        ELSE NULL
    END AS monthly_achievement_rate,
    CASE
        WHEN t.monthly_target IS NULL OR m.gmv IS NULL THEN NULL
        WHEN t.monthly_target > 0 THEN ROUND((m.gmv::numeric * 100.0 / t.monthly_target) - m.time_progress_pct, 2)
        WHEN t.monthly_target = 0 AND m.gmv = 0 THEN ROUND(0 - m.time_progress_pct, 2)
        ELSE NULL
    END AS time_gap,
    m.profit AS estimated_gross_profit,
    c.other_operating_cost,
    c.pre_commission_labor_cost,
    c.performance_labor_cost,
    c.commission_labor_cost,
    c.total_labor_cost,
    c.cost_status,
    c.estimated_expenses AS estimated_expenses,
    CASE
        WHEN m.profit IS NULL OR c.estimated_expenses IS NULL THEN NULL
        ELSE (m.profit - c.estimated_expenses)
    END AS operating_result,
    CASE
        WHEN m.profit IS NULL OR c.estimated_expenses IS NULL THEN NULL
        WHEN (m.profit - c.estimated_expenses) > 0 THEN '盈利'
        ELSE '亏损'
    END AS operating_result_text,
    m.order_count AS monthly_order_count,
    ds.order_count AS today_order_count
FROM base_month_kpi m
LEFT JOIN monthly_targets t
    ON m.period_month = t.period_month
   AND LOWER(COALESCE(m.platform_code, '')) = COALESCE(t.platform_code, '')
   AND COALESCE(m.shop_id, '') = COALESCE(t.shop_id, '')
LEFT JOIN monthly_costs c
    ON m.period_month = c.period_month
   AND LOWER(COALESCE(m.platform_code, '')) = COALESCE(c.platform_code, '')
   AND COALESCE(m.shop_id, '') = COALESCE(c.shop_id, '')
LEFT JOIN mart.shop_day_kpi ds
    ON ds.period_date = m.anchor_date
   AND ds.platform_code = m.platform_code
   AND COALESCE(ds.shop_id, '') = COALESCE(m.shop_id, '');
