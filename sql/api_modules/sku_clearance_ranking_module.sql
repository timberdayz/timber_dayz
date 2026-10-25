-- SKU 级滞销排名读模型
--
-- 2026-10-25 改造（判据换血 + 删假指标）：
--
-- 1. **主判据从「库龄」换成「距上次进货天数」**（`days_since_restock`）。
--    业务定义：西虹卖完不补货，偶尔补货；**补货才重新开始计时**，销售不重置。
--    数据来源：`mart.inventory_state`（每 SKU×仓 一行，周采集持续 upsert），
--    SKU 级取**各仓最长**（只算还有库存的仓）——一个仓压着没补货，这货整体就压着。
-- 2. **删掉 9999 哨兵与假指标**：estimated_turnover_days（含 9999）/
--    daily_avg_sales / is_stagnant / estimated_stagnant_days /
--    stagnant_snapshot_count / risk_level / clearance_priority_score
--    ——它们都不是「事实」，只是把口径错位包装成了分数。
-- 3. **DOS 只作参考**：视图给 `checklist_sales_90d`（妙手自带的窗口销量），
--    除法在 Python 的唯一实现里做（`backend/services/inventory/inventory_dos_service.py`），
--    SQL 里不写第二份公式。
-- 4. **定价字段刻意不放这里**：档位、折扣率、最低售价全部由后端 service 调
--    backend/services/product_pricing_service.py 的纯函数（select_age_tier /
--    compute_sku_pricing）补齐。在 SQL 里再写一遍公式 = 第二份口径，必然随规则表演进漂移。
--
-- ⚠️ **未匹配主数据的 SKU 照常保留**：不 join core.dim_erp_sku 过滤掉未匹配行，
--    滞销清单漏掉新品恰恰是最要命的。匹配不上的行定价字段为空，由前端标「未匹配主数据」。
--
-- ⚠️ 性能：sales_30d 的平台限定见下 —— 谓词下推把 21s 降到 12ms，数字不变。

CREATE SCHEMA IF NOT EXISTS api;

-- PostgreSQL 不能用 CREATE OR REPLACE 改视图列名/列序，这里是新建视图，
-- 但仍然先 DROP 一次，保证重复执行时列变更也能落地。
DROP VIEW IF EXISTS api.sku_clearance_ranking_module;

CREATE OR REPLACE VIEW api.sku_clearance_ranking_module AS
WITH state AS (
    -- 距上次进货天数（SKU 级）
    -- mart.inventory_state 每行是一个 SKU×仓：
    --   stock_added_at  = 上次库存数量增加（进货）的时间 = 计时器基准
    --   available_stock > 0 的仓才参与（已清空的仓不压资金）
    SELECT
        platform_code,
        sku_key,
        MAX(CURRENT_DATE - stock_added_at::date)        AS days_since_restock,
        SUM(COALESCE(available_stock, 0))              AS current_qty,
        SUM(COALESCE(on_hand_stock, 0))                AS on_hand_qty,
        SUM(COALESCE(inventory_value, 0))              AS inventory_value,
        COUNT(DISTINCT warehouse_name)                 AS warehouse_count,
        MAX(checklist_sales_90d)                       AS checklist_sales_90d,
        MAX(last_metric_date)                          AS snapshot_date
    FROM mart.inventory_state
    WHERE sku_key IS NOT NULL
      -- 只算**还有库存的仓**：已清空的仓不压资金，不参与天数与仓数聚合。
      -- 与 backend/services/inventory/inventory_restock_query_service.py 的取数口径逐字对齐
      -- （同一套公式 + 同一个过滤），商品中心与滞销清单不会给出两个答案。
      AND available_stock > 0
    GROUP BY platform_code, sku_key
),
sales_30d AS (
    -- 近 30 天动销（**参考值**）：按 SKU 聚合，不是按仓库行，否则同一 SKU 的销量会被重复计数
    -- 平台限定见文件头说明：谓词下推 → 21s 降到 12ms，数字不变。
    SELECT
        platform_code,
        product_sku,
        COALESCE(SUM(product_quantity), 0)         AS sold_units_30d,
        COUNT(DISTINCT metric_date::date)          AS active_days_30d
    FROM semantic.fact_orders_atomic
    WHERE platform_code = ANY (
              ARRAY(SELECT DISTINCT platform_code FROM mart.inventory_state)
          )
      AND metric_date::date >= CURRENT_DATE - INTERVAL '30 days'
      AND metric_date::date <= CURRENT_DATE
      AND product_sku IS NOT NULL
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
    s.snapshot_date,
    s.platform_code,
    s.sku_key                           AS product_sku,
    s.sku_key,
    COALESCE(erp.sku_name, s.sku_key)   AS product_name,
    s.current_qty,
    s.on_hand_qty,
    s.inventory_value,
    s.warehouse_count,
    -- 主判据
    s.days_since_restock,
    -- DOS 参考原料（除法在 Python 唯一实现里做）
    s.checklist_sales_90d,
    COALESCE(sd.sold_units_30d, 0)      AS sold_units_30d,
    erp.sku_id,
    erp.default_purchase_cost,
    erp.reference_selling_price,
    erp.min_selling_price_override
FROM state s
LEFT JOIN sales_30d sd
       ON sd.platform_code = s.platform_code
      AND sd.product_sku = s.sku_key
LEFT JOIN erp
       ON erp.sku_key = s.sku_key;
