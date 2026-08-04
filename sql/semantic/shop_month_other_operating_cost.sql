CREATE SCHEMA IF NOT EXISTS semantic;

CREATE OR REPLACE VIEW semantic.shop_month_other_operating_cost AS
SELECT
    to_date("年月" || '-01', 'YYYY-MM-DD') AS period_month,
    LOWER(TRIM(COALESCE(platform_code, ''))) AS platform_code,
    "店铺ID" AS shop_id,
    SUM(
        COALESCE(
            "成本合计",
            COALESCE("租金", 0)
            + COALESCE("营销费用", 0)
            + COALESCE("水电费", 0)
            + COALESCE("AI Token费用", 0)
            + COALESCE("人力费用", 0)
            + COALESCE("其他成本", 0)
        ) - COALESCE("人力费用", 0)
    ) AS other_operating_cost
FROM a_class.operating_costs
WHERE "删除时间" IS NULL
GROUP BY
    to_date("年月" || '-01', 'YYYY-MM-DD'),
    LOWER(TRIM(COALESCE(platform_code, ''))),
    "店铺ID";
