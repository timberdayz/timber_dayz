CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.business_overview_shop_racing_module AS
WITH base AS (
    SELECT
        'daily'::varchar AS granularity,
        period_date AS period_start,
        period_date AS period_end,
        period_date AS period_key,
        platform_code,
        shop_id,
        gmv,
        order_count,
        avg_order_value,
        attach_rate,
        profit
    FROM mart.shop_day_kpi
    UNION ALL
    SELECT
        'weekly'::varchar AS granularity,
        period_week AS period_start,
        (period_week + INTERVAL '6 day')::date AS period_end,
        period_week AS period_key,
        platform_code,
        shop_id,
        gmv,
        order_count,
        avg_order_value,
        attach_rate,
        profit
    FROM mart.shop_week_kpi
    UNION ALL
    SELECT
        'monthly'::varchar AS granularity,
        period_month AS period_start,
        (period_month + INTERVAL '1 month - 1 day')::date AS period_end,
        period_month AS period_key,
        platform_code,
        shop_id,
        gmv,
        order_count,
        avg_order_value,
        attach_rate,
        profit
    FROM mart.shop_month_kpi
),
targets AS (
    SELECT
        tb.platform_code,
        COALESCE(tb.shop_id, '') AS shop_id,
        tb.period_start,
        tb.period_end,
        COALESCE(SUM(tb.target_amount), 0) AS target_amount,
        COALESCE(MAX(tb.achievement_rate), 0) AS achievement_rate
    FROM a_class.target_breakdown tb
    INNER JOIN a_class.sales_targets st
        ON st.id = tb.target_id
       AND st.status = 'active'
    WHERE tb.breakdown_type IN ('shop', 'shop_time')
    GROUP BY tb.platform_code, COALESCE(tb.shop_id, ''), tb.period_start, tb.period_end
)
SELECT
    b.granularity,
    b.period_key,
    b.platform_code,
    b.shop_id,
    b.gmv,
    b.order_count,
    b.avg_order_value,
    b.attach_rate,
    b.profit,
    COALESCE(t.target_amount, 0) AS target_amount,
    CASE
        WHEN COALESCE(t.target_amount, 0) > 0
        THEN ROUND(b.gmv::numeric * 100.0 / t.target_amount, 2)
        ELSE COALESCE(t.achievement_rate, 0)
    END AS achievement_rate
FROM base b
LEFT JOIN targets t
    ON b.platform_code = t.platform_code
   AND COALESCE(b.shop_id, '') = COALESCE(t.shop_id, '')
   AND t.period_start <= b.period_end
   AND t.period_end >= b.period_start;
