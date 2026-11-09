CREATE SCHEMA IF NOT EXISTS semantic;

-- Current launch contract:
-- - a_class.operating_costs columns: shop_id, year_month, total_amount,
--   rent_amount, marketing_amount, utility_amount, ai_token_amount,
--   labor_amount, other_amount, is_locked, deleted_at (all English names).
-- - 手工「其他经营成本」口径 = 成本合计 - 人力费用（人力成本走 mart 层投影）。

CREATE OR REPLACE VIEW semantic.shop_month_other_operating_cost AS
SELECT
    to_date(year_month || '-01', 'YYYY-MM-DD') AS period_month,
    LOWER(TRIM(COALESCE(platform_code, ''))) AS platform_code,
    shop_id,
    SUM(
        COALESCE(
            total_amount,
            COALESCE(rent_amount, 0)
            + COALESCE(marketing_amount, 0)
            + COALESCE(utility_amount, 0)
            + COALESCE(ai_token_amount, 0)
            + COALESCE(labor_amount, 0)
            + COALESCE(other_amount, 0)
        ) - COALESCE(labor_amount, 0)
    ) AS other_operating_cost
FROM a_class.operating_costs
WHERE deleted_at IS NULL
GROUP BY
    to_date(year_month || '-01', 'YYYY-MM-DD'),
    LOWER(TRIM(COALESCE(platform_code, ''))),
    shop_id;
