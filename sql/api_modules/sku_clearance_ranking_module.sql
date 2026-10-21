-- SKU 级滞销排名读模型
--
-- 设计口径（docs/superpowers/specs/2026-10-21-sku-level-clearance-ranking-design.md §3）：
--
-- 1. **库龄主口径** = mart.inventory_age_current.age_days（真库龄：从第一次有库存起累加，
--    补货归零 / 卖空重现归零）。不是 estimated_stagnant_days（那个只是最近两帧间隔，
--    采集越密反而越小），也不是 estimated_turnover_days（那是动销速度）。
-- 2. **一行一个 SKU**：mart.inventory_age_current 本身就是 (platform_code, sku_key) 粒度。
-- 3. **动销辅助列在 SKU 层级重算**：mart.inventory_backlog_base 是仓库行（同一 SKU 可能多仓），
--    所以按 (platform_code, product_sku) 聚合后再算 estimated_turnover_days，不能直接 MAX。
-- 4. **风险等级改用库龄**：店铺级读模型 api.clearance_ranking_module 用 estimated_stagnant_days
--    比 30/60/90，SKU 级改用真库龄比 90/180，阈值与定价档位对齐。
--
-- ⚠️ **定价字段刻意不放这里**：档位、折扣率、最低售价全部由后端 service 调
--    backend/services/product_pricing_service.py 的纯函数（select_age_tier /
--    compute_sku_pricing）补齐。在 SQL 里再写一遍公式 = 第二份口径，必然随规则表演进漂移。
--    本视图只提供定价所需的**原料**：sku_id / default_purchase_cost /
--    reference_selling_price / min_selling_price_override / age_days。
--
-- ⚠️ **未匹配主数据的 SKU 照常保留**：不 join core.dim_erp_sku 过滤掉未匹配行，
--    滞销清单漏掉新品恰恰是最要命的。匹配不上的行定价字段为空，由前端标「未匹配主数据」。

CREATE SCHEMA IF NOT EXISTS api;

-- PostgreSQL 不能用 CREATE OR REPLACE 改视图列名/列序，这里是新建视图，
-- 但仍然先 DROP 一次，保证重复执行时列变更也能落地。
DROP VIEW IF EXISTS api.sku_clearance_ranking_module;

CREATE OR REPLACE VIEW api.sku_clearance_ranking_module AS
WITH age AS (
    -- 库龄主口径：每个 (platform_code, sku_key) 一行
    SELECT
        a.snapshot_date,
        a.platform_code,
        a.sku_key,
        a.product_sku,
        a.product_name,
        a.current_qty,
        a.on_hand_qty,
        a.inventory_value,
        a.warehouse_count,
        a.age_anchor_date,
        a.age_days,
        a.bucket                                   AS age_bucket,
        a.reset_reason
    FROM mart.inventory_age_current a
    WHERE a.product_sku IS NOT NULL
),
turnover AS (
    -- 动销辅助：backlog_base 是仓库行，这里聚合到 SKU
    SELECT
        platform_code,
        product_sku,
        SUM(COALESCE(available_stock, 0))          AS available_stock,
        SUM(COALESCE(on_hand_stock, 0))            AS on_hand_stock,
        SUM(COALESCE(inventory_value, 0))          AS inventory_value,
        SUM(COALESCE(daily_avg_sales, 0))          AS daily_avg_sales,
        CASE
            WHEN SUM(COALESCE(daily_avg_sales, 0)) > 0
            THEN ROUND(
                    SUM(COALESCE(available_stock, 0))::numeric
                    / SUM(COALESCE(daily_avg_sales, 0)),
                    2
                 )
            -- 没有动销数据但在库 = 卖不动，口径与 mart.inventory_backlog_base 保持一致
            WHEN SUM(COALESCE(available_stock, 0)) > 0 THEN 9999
            ELSE 0
        END                                         AS estimated_turnover_days,
        BOOL_OR(COALESCE(is_stagnant, FALSE))       AS is_stagnant,
        MAX(COALESCE(estimated_stagnant_days, 0))  AS estimated_stagnant_days,
        MAX(COALESCE(stagnant_snapshot_count, 0))  AS stagnant_snapshot_count
    FROM mart.inventory_backlog_base
    WHERE product_sku IS NOT NULL
    GROUP BY platform_code, product_sku
),
erp AS (
    -- ERP 主数据：只取定价需要的原料列
    SELECT
        sku_id,
        sku_key,
        sku_name,
        default_purchase_cost,
        reference_selling_price,
        min_selling_price_override
    FROM core.dim_erp_sku
)
SELECT
    a.snapshot_date,
    a.platform_code,
    a.product_sku,
    a.sku_key,
    COALESCE(erp.sku_name, a.product_name)          AS product_name,
    a.current_qty,
    a.on_hand_qty,
    a.inventory_value,
    a.warehouse_count,
    a.age_anchor_date,
    a.age_days,
    a.age_bucket,
    a.reset_reason,
    t.estimated_turnover_days,
    t.daily_avg_sales,
    t.is_stagnant,
    t.estimated_stagnant_days,
    t.stagnant_snapshot_count,
    CASE
        WHEN COALESCE(a.age_days, 0) >= 180 OR COALESCE(t.stagnant_snapshot_count, 0) >= 3 THEN 'high'
        WHEN COALESCE(a.age_days, 0) >= 90  OR COALESCE(t.stagnant_snapshot_count, 0) >= 2 THEN 'medium'
        ELSE 'low'
    END                                             AS risk_level,
    -- 清货优先级：库存金额为主，库龄加权，周转天数次之
    --
    -- 周转项做 90 天封顶：mart.inventory_backlog_base 的 estimated_turnover_days 用 9999
    -- 当「有库存但完全没有动销数据」的哨兵值，直接乘 2 会把分数整体推到 2 万以上，
    -- 运营看不懂。封顶后排序不变（当前所有 SKU 的周转项本来就是同一个常量），
    -- 分数回到「库存金额×0.5 + 库龄×10 + 最多 180」的可读区间。
    -- ⚠️ 目前所有 SKU 都没有动销数据（daily_avg_sales=0），estimated_turnover_days 恒为 9999，
    --    因此本分数实际由「库存金额×0.5 + 库龄×10」决定排序。
    ROUND(
        COALESCE(a.inventory_value, 0) * 0.5
        + COALESCE(a.age_days, 0) * 10
        + LEAST(COALESCE(t.estimated_turnover_days, 0), 90) * 2
    , 2)                                            AS clearance_priority_score,
    erp.sku_id,
    erp.default_purchase_cost,
    erp.reference_selling_price,
    erp.min_selling_price_override
FROM age a
LEFT JOIN turnover t
       ON t.platform_code = a.platform_code
      AND t.product_sku = a.product_sku
LEFT JOIN erp
       ON erp.sku_key = a.product_sku;
