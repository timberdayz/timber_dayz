CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.business_overview_operational_metrics_module AS
WITH day_anchors AS (
    SELECT
        m.period_month,
        m.platform_code,
        m.shop_id,
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
        to_date(year_month || '-01', 'YYYY-MM-DD') AS period_month,
        shop_id AS shop_id,
        COALESCE(SUM(target_sales_amount), 0) AS monthly_target
    FROM a_class.sales_targets_a
    GROUP BY to_date(year_month || '-01', 'YYYY-MM-DD'), shop_id
),
monthly_costs AS (
    SELECT
        to_date(year_month || '-01', 'YYYY-MM-DD') AS period_month,
        shop_id AS shop_id,
        COALESCE(SUM(rent + salary + utilities + other_costs), 0) AS estimated_expenses
    FROM a_class.operating_costs
    GROUP BY to_date(year_month || '-01', 'YYYY-MM-DD'), shop_id
),
daily_sales AS (
    SELECT
        d.period_date,
        d.platform_code,
        d.shop_id,
        d.gmv AS today_sales,
        d.order_count AS today_order_count
    FROM mart.shop_day_kpi d
)
SELECT
    m.period_month,
    m.platform_code,
    m.shop_id,
    COALESCE(t.monthly_target, 0) AS monthly_target,
    m.gmv AS monthly_total_achieved,
    COALESCE(ds.today_sales, 0) AS today_sales,
    CASE
        WHEN COALESCE(t.monthly_target, 0) > 0
        THEN ROUND(m.gmv::numeric * 100.0 / t.monthly_target, 2)
        ELSE 0
    END AS monthly_achievement_rate,
    CASE
        WHEN COALESCE(t.monthly_target, 0) > 0
        THEN ROUND((m.gmv::numeric * 100.0 / t.monthly_target) - da.time_progress_pct, 2)
        ELSE 0
    END AS time_gap,
    m.profit AS estimated_gross_profit,
    COALESCE(c.estimated_expenses, 0) AS estimated_expenses,
    (m.profit - COALESCE(c.estimated_expenses, 0)) AS operating_result,
    CASE
        WHEN (m.profit - COALESCE(c.estimated_expenses, 0)) > 0 THEN '盈利'
        ELSE '亏损'
    END AS operating_result_text,
    m.order_count AS monthly_order_count,
    COALESCE(ds.today_order_count, 0) AS today_order_count
FROM mart.shop_month_kpi m
LEFT JOIN day_anchors da
    ON m.period_month = da.period_month
   AND m.platform_code = da.platform_code
   AND COALESCE(m.shop_id, '') = COALESCE(da.shop_id, '')
LEFT JOIN monthly_targets t
    ON m.period_month = t.period_month
   AND COALESCE(m.shop_id, '') = COALESCE(t.shop_id, '')
LEFT JOIN monthly_costs c
    ON m.period_month = c.period_month
   AND COALESCE(m.shop_id, '') = COALESCE(c.shop_id, '')
LEFT JOIN daily_sales ds
    ON ds.period_date = da.anchor_date
   AND ds.platform_code = m.platform_code
   AND COALESCE(ds.shop_id, '') = COALESCE(m.shop_id, '');
