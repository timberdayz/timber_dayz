CREATE SCHEMA IF NOT EXISTS api;

-- PostgreSQL 不能用 CREATE OR REPLACE 改视图列名/列序 → 先 DROP 再建。
DROP VIEW IF EXISTS api.inventory_backlog_summary_module;

CREATE OR REPLACE VIEW api.inventory_backlog_summary_module AS
-- 2026-10-24：汇总口径从「周转天数分档」改为「距上次进货时长分档」。
-- ⚠️ 分档阈值在 SQL 里出现是**唯一例外**（这里只是汇总，不能跨语言分发）；
--    滞销模块与商品中心的**判定**分档一律走 inventory_restock_service 的唯一实现。
SELECT
    SUM(inventory_value) AS total_value,
    SUM(available_stock) AS total_quantity,
    -- 重度积压：停滞 ≥ 180 天
    SUM(CASE WHEN days_since_restock >= 180 THEN inventory_value ELSE 0 END) AS deep_stagnant_value,
    -- 中度积压：停滞 90 ~ 180 天
    SUM(
        CASE
            WHEN days_since_restock >= 90 AND days_since_restock < 180 THEN inventory_value
            ELSE 0
        END
    ) AS mid_stagnant_value,
    COUNT(*) FILTER (WHERE days_since_restock >= 180) AS deep_stagnant_row_count,
    COUNT(*) FILTER (WHERE days_since_restock >= 90 AND days_since_restock < 180) AS mid_stagnant_row_count,
    -- 停滞 < 30 天 = 还在动的货（快断货提示用，不进滞销榜）
    COUNT(*) FILTER (WHERE days_since_restock < 30) AS active_row_count,
    -- **去重 SKU 数**：本视图是 SKU×仓 粒度，卡片上写「SKU 数」就不能给行数
    COUNT(DISTINCT (platform_code, product_sku))
        FILTER (WHERE days_since_restock >= 180) AS deep_stagnant_sku_count,
    COUNT(DISTINCT (platform_code, product_sku))
        FILTER (WHERE days_since_restock >= 90 AND days_since_restock < 180) AS mid_stagnant_sku_count,
    COUNT(DISTINCT (platform_code, product_sku))
        FILTER (WHERE days_since_restock < 30) AS active_sku_count,
    -- 距上次进货时长取不到的行（状态层没这行）：单独暴露，不静默当成「活跃」
    COUNT(*) FILTER (WHERE days_since_restock IS NULL) AS unknown_restock_row_count
FROM mart.inventory_backlog_base;
