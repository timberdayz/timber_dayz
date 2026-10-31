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
-- 2026-10-31 「近30天动销」换源（`sold_units_30d` 恒 0 的根因修复）：
--
-- 现象：这一列**永远是 0**（不是"偶尔为 0"，是 100% 为 0）。
--
-- 根因不是数据没到位，是**跨系统对账**这件事本身就不成立：
--   ① **平台对不上**：库存行来自妙手（platform_code='miaoshou'），
--      订单行来自销售渠道（shopee / tiktok）。老口径用 platform_code 相等连接，
--      妙手库存永远配不上任何销售渠道的订单 ⇒ 一行都配不上。
--      （老代码还额外加了 `platform_code = ANY(有库存的平台)` 过滤，
--        在生产上直接把 shopee/tiktok 的订单行全滤掉 —— 快是快了，数字是全 0。）
--   ② **SKU 口径不一致**：订单侧只取 `product_sku`；库存侧取的是
--      `platform_sku → product_sku → sku_id → product_id` 的组合。同一件商品
--      两个系统给的键不一样。
--   ③ **大小写不归一**：`'A-00001-Army green'` vs `'A-00001-Army Green'` 配不上。
--
-- 改法：**不再跨系统对账**，直接用妙手 ERP 自带的「近30天销量」
--        （原始列名「近30天销量数据」→ `checklist_sales_30d`）。
--   - 库存与销量来自**同一次采集、同一份文件** ⇒ 库存和销量不会互相打架；
--   - 数字是真的：本地实测 ERP 口径与订单事实口径的均值几乎相同
--     （6.76 vs 6.79）；两边都 >0 的 246 个 SKU 里 189 个差异 ≤20%，
--     差异来自采集时点不同，不是口径打架；
--   - 页面从「10 秒级慢查询」变成「毫秒级」：不再扫 `semantic.fact_orders_atomic`
--     （那个视图每行都要跑一次店铺别名解析，本地实测 2253 行 = 10.6 秒）。
--
-- ⚠️ 语义变化（业务须知）：`sold_units_30d` 现在是**妙手口径的 SKU 级近30天销量**
--    （跨渠道合计），不再是「某个销售渠道的订单销量」。滞销清单按 SKU 展示，
--    运营在妙手看到的近30天销量与这里一致 —— 这正是本轮重构要的口径统一。
--    同一 SKU 若在多个 platform 下都有库存行，各行显示同一个 SKU 级销量值。
--
-- ⚠️ 性能：视图只读 `mart.inventory_state` 与 `core.dim_erp_sku`，
--    实测 0.4ms。不再依赖 `semantic.fact_orders_atomic`。

CREATE SCHEMA IF NOT EXISTS api;

-- PostgreSQL 不能用 CREATE OR REPLACE 改视图列名/列序，这里是新建视图，
-- 但仍然先 DROP 一次，保证重复执行时列变更也能落地。
DROP VIEW IF EXISTS api.sku_clearance_ranking_module;

CREATE OR REPLACE VIEW api.sku_clearance_ranking_module AS
WITH state AS (
    -- 距上次进货天数（SKU 级）+ 妙手窗口销量
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
        -- DOS 参考原料（妙手「近90天销量数据」）
        MAX(checklist_sales_90d)                       AS checklist_sales_90d,
        -- 近30天动销（妙手「近30天销量数据」）：与库存同源、同一次采集
        MAX(checklist_sales_30d)                       AS sold_units_30d,
        MAX(last_metric_date)                          AS snapshot_date
    FROM mart.inventory_state
    WHERE sku_key IS NOT NULL
      -- 只算**还有库存的仓**：已清空的仓不压资金，不参与天数与仓数聚合。
      -- 与 backend/services/inventory/inventory_restock_query_service.py 的取数口径逐字对齐
      -- （同一套公式 + 同一个过滤），商品中心与滞销清单不会给出两个答案。
      AND available_stock > 0
    GROUP BY platform_code, sku_key
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
    -- 近30天动销（参考值）
    COALESCE(s.sold_units_30d, 0)       AS sold_units_30d,
    erp.sku_id,
    erp.default_purchase_cost,
    erp.reference_selling_price,
    erp.min_selling_price_override
FROM state s
LEFT JOIN erp
       ON erp.sku_key = s.sku_key;
