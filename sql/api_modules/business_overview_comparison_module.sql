CREATE SCHEMA IF NOT EXISTS api;

-- Current launch contract:
-- - 店铺月度目标的真 SSOT 是 a_class.target_breakdown（breakdown_type='shop'）
--   + 其父目标 a_class.sales_targets；
-- - a_class.sales_targets_a 已于第三批-C 迁移中下线（表已 DROP）。
-- - 月份键：target_breakdown.period_label（'YYYY-MM'，仓库既有「店铺月度档位」约定）。

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
        COALESCE(page_views, visitor_count) AS traffic,
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
        COALESCE(page_views, visitor_count) AS traffic,
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
        to_date(tb.period_label || '-01', 'YYYY-MM-DD') AS period_month,
        LOWER(TRIM(COALESCE(tb.platform_code, ''))) AS platform_code,
        tb.shop_id,
        ROUND(COALESCE(SUM(tb.target_amount), 0)::numeric, 2) AS target_sales_amount,
        COALESCE(SUM(tb.target_quantity), 0)::bigint AS target_sales_quantity
    FROM a_class.target_breakdown tb
    JOIN a_class.sales_targets st ON st.id = tb.target_id
    WHERE tb.breakdown_type = 'shop'
      AND st.target_type = 'shop'
      AND st.status = 'active'
      AND tb.period_label ~ '^\d{4}-\d{2}$'
    GROUP BY
        to_date(tb.period_label || '-01', 'YYYY-MM-DD'),
        LOWER(TRIM(COALESCE(tb.platform_code, ''))),
        tb.shop_id
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
        COALESCE(m.page_views, m.visitor_count) AS traffic,
        m.conversion_rate,
        m.avg_order_value,
        m.attach_rate,
        m.profit,
        t.target_sales_amount,
        t.target_sales_quantity
    FROM mart.shop_month_kpi m
    LEFT JOIN monthly_target t
        ON m.period_month = t.period_month
       AND LOWER(COALESCE(m.platform_code, '')) = COALESCE(t.platform_code, '')
       AND COALESCE(m.shop_id, '') = COALESCE(t.shop_id, '')
)
SELECT * FROM daily
UNION ALL
SELECT * FROM weekly
UNION ALL
SELECT * FROM monthly;
