CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.annual_summary_trend_module AS
WITH monthly_costs AS (
    SELECT
        to_date("年月" || '-01', 'YYYY-MM-DD') AS period_month,
        SUM("租金" + "营销费用" + "水电费" + "其他成本") AS total_cost
    FROM a_class.operating_costs
    GROUP BY to_date("年月" || '-01', 'YYYY-MM-DD')
),
monthly_kpi AS (
    SELECT
        period_month,
        SUM(gmv) AS gmv,
        SUM(profit) AS profit
    FROM mart.platform_month_kpi
    GROUP BY period_month
)
SELECT
    k.period_month,
    k.gmv,
    c.total_cost,
    k.profit
FROM monthly_kpi k
LEFT JOIN monthly_costs c
    ON k.period_month = c.period_month;
