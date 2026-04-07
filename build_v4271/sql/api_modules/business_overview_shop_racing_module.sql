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
        ELSE 0::numeric
    END AS achievement_rate
FROM base b
LEFT JOIN LATERAL (
    WITH shop_target AS (
        SELECT COALESCE(SUM(tb.target_amount)::numeric, 0::numeric) AS target_amount
        FROM a_class.target_breakdown tb
        INNER JOIN a_class.sales_targets st
            ON st.id = tb.target_id
           AND st.status = 'active'
        WHERE tb.breakdown_type = 'shop'
          AND tb.platform_code = b.platform_code
          AND COALESCE(tb.shop_id, '') = COALESCE(b.shop_id, '')
          AND tb.period_start <= b.period_end
          AND tb.period_end >= b.period_start
    ),
    shop_time_target AS (
        SELECT COALESCE(SUM(tb.target_amount)::numeric, 0::numeric) AS target_amount
        FROM a_class.target_breakdown tb
        INNER JOIN a_class.sales_targets st
            ON st.id = tb.target_id
           AND st.status = 'active'
        WHERE tb.breakdown_type = 'shop_time'
          AND tb.platform_code = b.platform_code
          AND COALESCE(tb.shop_id, '') = COALESCE(b.shop_id, '')
          AND tb.period_start <= b.period_end
          AND tb.period_end >= b.period_start
    )
    SELECT
        CASE
            WHEN b.granularity = 'monthly' AND (SELECT target_amount FROM shop_target) > 0
            THEN (SELECT target_amount FROM shop_target)
            WHEN (SELECT target_amount FROM shop_time_target) > 0
            THEN (SELECT target_amount FROM shop_time_target)
            ELSE (SELECT target_amount FROM shop_target)
        END AS target_amount
) t ON TRUE;
