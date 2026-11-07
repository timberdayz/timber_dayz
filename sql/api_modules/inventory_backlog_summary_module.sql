CREATE SCHEMA IF NOT EXISTS api;

-- PostgreSQL 不能用 CREATE OR REPLACE 改视图列名/列序 → 先 DROP 再建。
DROP VIEW IF EXISTS api.inventory_backlog_summary_module;

CREATE OR REPLACE VIEW api.inventory_backlog_summary_module AS
-- 2026-11-29：新增**业务定价档位**分组（0 / 60 / 90 / 120）。
--
-- 为什么
-- --------
-- 旧口径只有 <30 / 90~180 / >=180 三档，**30~90 天整段无档**：
-- 业务上 60 天起就要打折（算滞销），看板却把这段显示成「活跃」；
-- 而且行数 / SKU 数只覆盖 <30 的行，与「货值是全量」自相矛盾。
--
-- 分档粒度：SKU 级
-- ----------------
-- 商品中心的定价是 **SKU 级**（一个仓压着没补货，就是这货整体压着），
-- 所以档位必须按 **SKU** 算：库龄 = 各仓**最长**（只算还有可售库存的仓），
-- 货值 = 该 SKU 全部仓的货值之和 ⇒ SKU 数与货值都**互斥可加**。
-- 这与 Python 侧 ``aggregate_sku_restock_tier``（唯一实现）逐条一致，
-- 由 ``backend/tests/data_pipeline/test_inventory_backlog_tier_consistency.py``
-- 锁定。
--
-- 阈值**不写死在本文件**：直接读 ``finance.sku_pricing_policies`` 当前生效行
-- —— 业务改档位表，看板自动跟着变，不需要改 SQL。
--
-- ⚠ 旧标准指标（``deep_stagnant_value`` ≥180 天 / ``mid_stagnant_value`` 90~180 天）
--    是「深度积压」这一**独立指标**（见指标词典），口径**保持不变**；
--    档位分组是**新增**的，不替换它们。
WITH base AS (
    SELECT
        COALESCE(inventory_value, 0) AS inventory_value,
        COALESCE(available_stock, 0) AS available_stock,
        days_since_restock,
        platform_code,
        product_sku
    FROM mart.inventory_backlog_base
),
policy AS (
    SELECT min_restock_days, tier_label
    FROM finance.sku_pricing_policies
    WHERE status = 'active' AND effective_to IS NULL
),
-- SKU 级聚合：库龄 = 各仓**最长**（只算还有可售库存的仓）
sku AS (
    SELECT
        platform_code,
        product_sku,
        MAX(days_since_restock) FILTER (WHERE available_stock > 0) AS sku_days,
        SUM(inventory_value) AS sku_value,
        COUNT(*) AS sku_row_count
    FROM base
    GROUP BY platform_code, product_sku
),
assigned AS (
    SELECT
        s.platform_code,
        s.product_sku,
        s.sku_value,
        s.sku_row_count,
        1 AS row_marker,
        -- 命中的**最高**门槛；低于最低门槛的行归到最低门槛（不静默漏掉）
        COALESCE(
            (
                SELECT MAX(p.min_restock_days)
                FROM policy p
                WHERE p.min_restock_days <= s.sku_days
            ),
            (SELECT MIN(p.min_restock_days) FROM policy p)
        ) AS tier_threshold
    FROM sku s
    WHERE s.sku_days IS NOT NULL
),
tiers AS (
    SELECT
        p.min_restock_days,
        p.tier_label,
        COALESCE(SUM(a.sku_row_count), 0) AS row_count,
        COUNT(a.row_marker) AS sku_count,
        COALESCE(SUM(a.sku_value), 0) AS inventory_value
    FROM policy p
    LEFT JOIN assigned a ON a.tier_threshold = p.min_restock_days
    GROUP BY p.min_restock_days, p.tier_label
)
SELECT
    SUM(inventory_value) AS total_value,
    SUM(available_stock) AS total_quantity,
    -- **全量**行数 / SKU 数：与 total_value 同口径
    -- （修掉「货值是全量、行数只覆盖一部分」的自相矛盾）
    COUNT(*) AS total_row_count,
    COUNT(DISTINCT (platform_code, product_sku)) AS total_sku_count,
    -- 距上次进货时长取不到的行：单独暴露，不静默当成「活跃」
    COUNT(*) FILTER (WHERE days_since_restock IS NULL) AS unknown_restock_row_count,
    -- 旧标准指标（口径不变：>=180 天 / 90~180 天）
    SUM(CASE WHEN days_since_restock >= 180 THEN inventory_value ELSE 0 END) AS deep_stagnant_value,
    SUM(
        CASE
            WHEN days_since_restock >= 90 AND days_since_restock < 180 THEN inventory_value
            ELSE 0
        END
    ) AS mid_stagnant_value,
    COUNT(*) FILTER (WHERE days_since_restock >= 180) AS deep_stagnant_row_count,
    COUNT(*) FILTER (WHERE days_since_restock >= 90 AND days_since_restock < 180) AS mid_stagnant_row_count,
    -- **去重 SKU 数**：本视图是 SKU×仓 粒度，卡片上写「SKU 数」就不能给行数
    COUNT(DISTINCT (platform_code, product_sku))
        FILTER (WHERE days_since_restock >= 180) AS deep_stagnant_sku_count,
    COUNT(DISTINCT (platform_code, product_sku))
        FILTER (WHERE days_since_restock >= 90 AND days_since_restock < 180) AS mid_stagnant_sku_count,
    COUNT(DISTINCT (platform_code, product_sku))
        FILTER (WHERE days_since_restock < 30) AS active_sku_count,
    -- 业务定价档位分组（SKU 级，门槛来自 policy 表）
    COALESCE(
        (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'min_restock_days', t.min_restock_days,
                    'tier_label', t.tier_label,
                    'row_count', t.row_count,
                    'sku_count', t.sku_count,
                    'inventory_value', t.inventory_value
                )
                ORDER BY t.min_restock_days
            )
            FROM tiers t
        ),
        '[]'::jsonb
    ) AS restock_tiers
FROM base;
