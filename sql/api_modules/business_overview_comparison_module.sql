CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.business_overview_comparison_module AS
WITH daily AS (
    SELECT
        'daily'::varchar AS granularity,
        period_date AS period_start,
        period_date AS period_end,
        period_date AS period_key,
        platform_code,
        shop_id,
        gmv AS sales_amount,
        order_count AS sales_quantity,
        visitor_count AS traffic,
        conversion_rate,
        avg_order_value,
        attach_rate,
        profit,
        NULL::numeric AS target_sales_amount,
        NULL::numeric AS target_sales_quantity
    FROM mart.shop_day_kpi
),
weekly AS (
    SELECT
        'weekly'::varchar AS granularity,
        period_week AS period_start,
        (period_week + INTERVAL '6 day')::date AS period_end,
        period_week AS period_key,
        platform_code,
        shop_id,
        gmv AS sales_amount,
        order_count AS sales_quantity,
        visitor_count AS traffic,
        conversion_rate,
        avg_order_value,
        attach_rate,
        profit,
        NULL::numeric AS target_sales_amount,
        NULL::numeric AS target_sales_quantity
    FROM mart.shop_week_kpi
),
monthly_target AS (
    SELECT
        to_date("年月" || '-01', 'YYYY-MM-DD') AS period_month,
        "店铺ID" AS shop_id,
        COALESCE(SUM("目标销售额"), 0) AS target_sales_amount,
        COALESCE(SUM("目标单量"), 0) AS target_sales_quantity
    FROM a_class.sales_targets_a
    GROUP BY to_date("年月" || '-01', 'YYYY-MM-DD'), "店铺ID"
),
monthly AS (
    SELECT
        'monthly'::varchar AS granularity,
        m.period_month AS period_start,
        (m.period_month + INTERVAL '1 month - 1 day')::date AS period_end,
        m.period_month AS period_key,
        m.platform_code,
        m.shop_id,
        m.gmv AS sales_amount,
        m.order_count AS sales_quantity,
        m.visitor_count AS traffic,
        m.conversion_rate,
        m.avg_order_value,
        m.attach_rate,
        m.profit,
        t.target_sales_amount,
        t.target_sales_quantity
    FROM mart.shop_month_kpi m
    LEFT JOIN monthly_target t
        ON m.period_month = t.period_month
       AND COALESCE(m.shop_id, '') = COALESCE(t.shop_id, '')
)
SELECT * FROM daily
UNION ALL
SELECT * FROM weekly
UNION ALL
SELECT * FROM monthly;
