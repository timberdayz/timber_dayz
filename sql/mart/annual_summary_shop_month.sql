CREATE SCHEMA IF NOT EXISTS mart;

-- Legacy operating_costs columns may include: "年月", "店铺ID", "租金", "工资", "水电费", "其他成本"
DO $bootstrap$
DECLARE
    marketing_fee_expr text;
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'a_class'
          AND table_name = 'operating_costs'
          AND column_name = '营销费用'
    ) THEN
        marketing_fee_expr := 'COALESCE("营销费用", 0)';
    ELSIF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'a_class'
          AND table_name = 'operating_costs'
          AND column_name = '工资'
    ) THEN
        marketing_fee_expr := 'COALESCE("工资", 0)';
    ELSE
        marketing_fee_expr := '0';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'a_class'
          AND table_name = 'operating_costs'
          AND column_name = 'year_month'
    ) THEN
        EXECUTE $view$
        CREATE OR REPLACE VIEW mart.annual_summary_shop_month AS
        WITH monthly_costs AS (
            SELECT
                to_date(year_month || '-01', 'YYYY-MM-DD') AS period_month,
                shop_id AS shop_id,
                SUM(rent + marketing_fee + utilities + other_costs) AS total_cost
            FROM a_class.operating_costs
            GROUP BY to_date(year_month || '-01', 'YYYY-MM-DD'), shop_id
        )
        SELECT
            m.period_month,
            m.platform_code,
            m.shop_id,
            m.gmv,
            m.order_count,
            COALESCE(m.page_views, m.visitor_count) AS visitor_count,
            m.conversion_rate,
            m.avg_order_value,
            m.attach_rate,
            m.profit,
            c.total_cost,
            CASE
                WHEN m.gmv IS NULL OR m.profit IS NULL THEN NULL
                WHEN m.gmv > 0 THEN ROUND(m.profit::numeric * 100.0 / m.gmv, 2)
                WHEN m.gmv = 0 AND m.profit = 0 THEN 0
                ELSE NULL
            END AS gross_margin,
            CASE
                WHEN m.gmv IS NULL OR m.profit IS NULL OR c.total_cost IS NULL THEN NULL
                WHEN m.gmv > 0 THEN ROUND((m.profit - c.total_cost)::numeric * 100.0 / m.gmv, 2)
                WHEN m.gmv = 0 AND m.profit = 0 AND c.total_cost = 0 THEN 0
                ELSE NULL
            END AS net_margin,
            CASE
                WHEN m.profit IS NULL OR c.total_cost IS NULL THEN NULL
                WHEN c.total_cost > 0 THEN ROUND((m.profit - c.total_cost)::numeric / c.total_cost, 2)
                WHEN c.total_cost = 0 AND m.profit = 0 THEN 0
                ELSE NULL
            END AS roi
        FROM mart.shop_month_kpi m
        LEFT JOIN monthly_costs c
            ON m.period_month = c.period_month
           AND COALESCE(m.shop_id, '') = COALESCE(c.shop_id, '')
        $view$;
    ELSE
        EXECUTE format($view$
        CREATE OR REPLACE VIEW mart.annual_summary_shop_month AS
        WITH monthly_costs AS (
            SELECT
                to_date("年月" || '-01', 'YYYY-MM-DD') AS period_month,
                "店铺ID" AS shop_id,
                SUM("租金" + %s + "水电费" + "其他成本") AS total_cost
            FROM a_class.operating_costs
            GROUP BY to_date("年月" || '-01', 'YYYY-MM-DD'), "店铺ID"
        )
        SELECT
            m.period_month,
            m.platform_code,
            m.shop_id,
            m.gmv,
            m.order_count,
            COALESCE(m.page_views, m.visitor_count) AS visitor_count,
            m.conversion_rate,
            m.avg_order_value,
            m.attach_rate,
            m.profit,
            c.total_cost,
            CASE
                WHEN m.gmv IS NULL OR m.profit IS NULL THEN NULL
                WHEN m.gmv > 0 THEN ROUND(m.profit::numeric * 100.0 / m.gmv, 2)
                WHEN m.gmv = 0 AND m.profit = 0 THEN 0
                ELSE NULL
            END AS gross_margin,
            CASE
                WHEN m.gmv IS NULL OR m.profit IS NULL OR c.total_cost IS NULL THEN NULL
                WHEN m.gmv > 0 THEN ROUND((m.profit - c.total_cost)::numeric * 100.0 / m.gmv, 2)
                WHEN m.gmv = 0 AND m.profit = 0 AND c.total_cost = 0 THEN 0
                ELSE NULL
            END AS net_margin,
            CASE
                WHEN m.profit IS NULL OR c.total_cost IS NULL THEN NULL
                WHEN c.total_cost > 0 THEN ROUND((m.profit - c.total_cost)::numeric / c.total_cost, 2)
                WHEN c.total_cost = 0 AND m.profit = 0 THEN 0
                ELSE NULL
            END AS roi
        FROM mart.shop_month_kpi m
        LEFT JOIN monthly_costs c
            ON m.period_month = c.period_month
           AND COALESCE(m.shop_id, '') = COALESCE(c.shop_id, '')
        $view$, marketing_fee_expr);
    END IF;
END
$bootstrap$;
