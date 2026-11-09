CREATE SCHEMA IF NOT EXISTS mart;

-- 店铺/月 人力成本视图（薪资链路的对外出口）。
--
-- ⚠️ 必须按 calculation_version 过滤，只认**当前**口径：
-- `finance.employee_labor_cost_allocations` 里可能残留历史旧口径行
-- （旧迁移脚本是「原地 UPDATE」，遇到受保护工资月会跳过 ⇒ 那些月仍是旧口径）
-- 以及同月新建的当前口径行。不加这个过滤 ⇒ 同一个人力成本被计入两次
-- ⇒ 看板经营指标里的「人力成本」虚高。
-- 口径基准见 backend/services/profit_basis_service.py（那边是按版本过滤的）。
-- ⚠️ 这里写死字符串是为了让视图定义自包含；该字面量必须与
-- backend/services/labor_cost_projection_service.py 的
-- LABOR_COST_CALCULATION_VERSION 一致
-- （一致性由 backend/tests/test_labor_cost_allocation_version.py 守护）。
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
  AND calculation_version = 'LABOR_COST_ALLOC_V1'
GROUP BY
    to_date(period_month || '-01', 'YYYY-MM-DD'),
    LOWER(TRIM(COALESCE(platform_code, ''))),
    shop_id;
