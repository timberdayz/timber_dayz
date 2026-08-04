CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.shop_month_labor_cost AS
SELECT
    to_date(period_month || '-01', 'YYYY-MM-DD') AS period_month,
    LOWER(TRIM(COALESCE(platform_code, ''))) AS platform_code,
    shop_id,
    SUM(pre_commission_amount) AS pre_commission_labor_cost,
    SUM(performance_amount) AS performance_labor_cost,
    SUM(commission_amount) AS commission_labor_cost,
    SUM(total_amount) AS total_labor_cost,
    CASE
        WHEN BOOL_AND(source_payroll_status IN ('confirmed', 'paid')) THEN 'confirmed'
        ELSE 'projected'
    END AS cost_status
FROM finance.employee_labor_cost_allocations
WHERE allocation_scope = 'shop'
GROUP BY
    to_date(period_month || '-01', 'YYYY-MM-DD'),
    LOWER(TRIM(COALESCE(platform_code, ''))),
    shop_id;
