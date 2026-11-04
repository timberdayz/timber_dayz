CREATE SCHEMA IF NOT EXISTS mart;

-- 店铺/月 人力成本视图（薪资链路的对外出口）。
--
-- ⚠️ 必须按 calculation_version 过滤，只认 V2 口径：
-- `finance.employee_labor_cost_allocations` 里同时可能存在历史 V1 行
-- （迁移脚本是「原地 UPDATE 成 V2」，遇到受保护工资月会跳过 ⇒ 那些月仍是 V1）
-- 以及同月新建的 V2 行。不加这个过滤 ⇒ 同一个人力成本被计入两次
-- ⇒ 看板经营指标里的「人力成本」虚高。
-- 口径基准见 backend/services/profit_basis_service.py（那边是按版本过滤的）。
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
        WHEN BOOL_AND(source_payroll_status IN ('approved', 'confirmed', 'paid')) THEN 'confirmed'
        ELSE 'projected'
    END AS cost_status
FROM finance.employee_labor_cost_allocations
WHERE allocation_scope = 'shop'
  AND calculation_version = 'LABOR_COST_V2'
GROUP BY
    to_date(period_month || '-01', 'YYYY-MM-DD'),
    LOWER(TRIM(COALESCE(platform_code, ''))),
    shop_id;
