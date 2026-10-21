-- SKU 级滞销排名读模型
--
-- 设计口径（docs/superpowers/specs/2026-10-21-sku-level-clearance-ranking-design.md §3）：
--
-- 1. **库龄主口径** = mart.inventory_age_current.age_days（真库龄：从第一次有库存起累加，
--    补货归零 / 卖空重现归零）。不是 estimated_stagnant_days（那个只是最近两帧间隔，
--    采集越密反而越小），也不是 estimated_turnover_days（那是动销速度）。
-- 2. **一行一个 SKU**：mart.inventory_age_current 本身就是 (platform_code, sku_key) 粒度。
-- 3. **动销辅助列在 SKU 层级重算**：库存/滞留列来自 mart.inventory_snapshot_change
--    （仓库行），按 (platform_code, product_sku) 聚合后再算 estimated_turnover_days。
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
--
-- ⚠️ **性能：为什么 sales_30d 要限定平台**
--    semantic.fact_orders_atomic 对 shopee/tiktok 的 2.8 万行做去重窗口，
--    全量求值要 **21 秒**；而 mart.inventory_backlog_base 的 sales_30d 用
--    `metric_date::date` 过滤，谓词下不进底层扫描，单是这一段就要 **8.8 秒**。
--    滞销清单是交互页面，8.8 秒不可接受。
--
--    这里把销售聚合限定在「有库存的平台」：
--      * platform_code 来自 mart.inventory_age_current（子查询 → InitPlan → 常量数组），
--        谓词能直接下推到 fact_orders_atomic 的 UNION ALL 分支，只扫对应平台的事实表；
--      * **不改变任何数字**：销售聚合与库存的连接键含 platform_code，
--        没有库存的平台其销售行本来也匹配不上。
--    实测：21.0s → 12ms。
--
--    库存/滞留列改从 mart.inventory_snapshot_change 取，不再经过 mart.inventory_backlog_base：
--    它与 mart.inventory_snapshot_latest 共用同一个 company_daily CTE 和同一个
--    ROW_NUMBER() 窗口 PARTITION BY，rank=1 的 available_stock / on_hand_stock /
--    inventory_value **完全等价**，但它不需要销售 CTE，代价只有 48ms。

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
stock AS (
    -- 仓库行 → SKU 行：库存与滞留指标
    -- mart.inventory_snapshot_change 与 mart.inventory_snapshot_latest 同源同窗口，
    -- rank=1 的库存口径等价，但不牵动销售 CTE。
    SELECT
        platform_code,
        product_sku,
        SUM(COALESCE(available_stock, 0))         AS available_stock,
        BOOL_OR(COALESCE(is_stagnant, FALSE))      AS is_stagnant,
        MAX(COALESCE(estimated_stagnant_days, 0))  AS estimated_stagnant_days,
        MAX(COALESCE(stagnant_snapshot_count, 0))  AS stagnant_snapshot_count
    FROM mart.inventory_snapshot_change
    WHERE product_sku IS NOT NULL
    GROUP BY platform_code, product_sku
),
sales_30d AS (
    -- 近 30 天动销：**按 SKU** 聚合（不是按仓库行，否则同一 SKU 的销量会被重复计数）
    -- 平台限定见文件头说明：谓词下推 → 21s 降到 12ms，数字不变。
    SELECT
        platform_code,
        product_sku,
        COALESCE(SUM(product_quantity), 0)         AS sold_units_30d,
        COUNT(DISTINCT metric_date::date)          AS active_days_30d
    FROM semantic.fact_orders_atomic
    WHERE platform_code = ANY (
              ARRAY(SELECT DISTINCT platform_code FROM mart.inventory_age_current)
          )
      AND metric_date::date >= CURRENT_DATE - INTERVAL '30 days'
      AND metric_date::date <= CURRENT_DATE
      AND product_sku IS NOT NULL
    GROUP BY platform_code, product_sku
),
turnover AS (
    SELECT
        st.platform_code,
        st.product_sku,
        st.available_stock,
        st.is_stagnant,
        st.estimated_stagnant_days,
        st.stagnant_snapshot_count,
        COALESCE(
            ROUND(
                s.sold_units_30d::numeric / NULLIF(s.active_days_30d, 0),
                2
            ),
            0
        )                                          AS daily_avg_sales,
        CASE
            WHEN COALESCE(s.sold_units_30d, 0) > 0
             AND COALESCE(s.active_days_30d, 0) > 0
            THEN ROUND(
                    st.available_stock::numeric
                    / NULLIF(s.sold_units_30d::numeric / s.active_days_30d, 0),
                    2
                 )
            -- 有库存但完全没有动销数据 = 卖不动，口径与 mart.inventory_backlog_base 保持一致
            WHEN COALESCE(st.available_stock, 0) > 0 THEN 9999
            ELSE 0
        END                                        AS estimated_turnover_days
    FROM stock st
    LEFT JOIN sales_30d s
           ON s.platform_code = st.platform_code
          AND s.product_sku = st.product_sku
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
