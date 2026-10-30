CREATE SCHEMA IF NOT EXISTS api;

-- The previous view exposed a different leading-column contract. PostgreSQL
-- cannot rename view columns through CREATE OR REPLACE VIEW, so rebuild it.
DROP VIEW IF EXISTS api.clearance_ranking_module;

-- 2026-10-30 慢查询治理（语义保持不变，只改执行方式）：
-- 原实现跑满 120 秒 DB statement_timeout 才报错（前端 70 秒先超时 -> 报「网络连接 70000ms」）。
-- 三个成本来源与对应改法：
--   1) `to_jsonb(o)->>'...'` 把整行（含 raw_data / header_columns 两个大 JSONB）
--      转成 jsonb 再取 key —— 对 b_class 下 9 张订单事实表逐行做一遍。
--      改法：直接取列（atomic 视图已经把 sku_id / platform_sku / product_sku /
--      product_id / paid_amount / sales_amount / product_quantity 暴露成普通列，
--      取值与 to_jsonb(o)->>'...' 完全一致）。
--   2) 金额上多做了一次 `numeric -> text -> 正则 -> numeric` 往返。
--      改法：atomic 视图的 paid_amount / sales_amount 只可能是 NULL 或有限 numeric
--      （源头是 regexp_replace('[^0-9.-]','') 清洗后的字符串再转 numeric），
--      原正则恒为真，故 COALESCE 与原表达式等价。
--   3) `JOIN LATERAL` 里的 `mart.inventory_backlog_base` 会被逐条订单行重复计算
--      （该视图自身还带两层窗口函数）—— 典型 N+1 放大。
--      改法：backlog 物化成 CTE（只算一次），LATERAL 的驱动行去重成
--      (ranking_month, platform_code, sku_key) —— LATERAL 的选行结果只取决于这三个字段，
--      去重不改变结果。
-- 选行规则（LATERAL + DISTINCT ON + NOT EXISTS + age_days >= 30）与输出列全部保持原样。
--
-- 2026-10-31 修 P7「恒 0 行」：两侧 SKU 口径不对称 + 跨域平台比较
-- ------------------------------------------------------------------
-- 现象：`api.clearance_ranking_module` 一直返回 0 行。
-- 实测根因有两条，**都出在本视图自己身上**，不是数据没到位：
--
--   ① **两侧 sku_key 定义不对称**
--      订单侧：`sku_id → platform_sku → product_sku → product_id`（sku_id 优先）
--      积压侧：`platform_sku → product_sku → product_id`（没有 sku_id）
--      同一个 SKU 在两侧算出**两个不同的 key** ⇒ 即使平台能对上也永远 join 不上。
--      修法：两侧统一成**同一个表达式** `platform_sku → product_sku → product_id`。
--      为什么订单侧也去掉 sku_id：积压视图 `mart.inventory_backlog_base`
--      根本不提供 sku_id 列（它来自妙手 ERP 快照），key 必须用**两侧都表达得出**
--      的列来算，否则又变成不对称。sku_id 只在 platform_sku / product_sku 都缺时
--      才轮到，而积压侧 platform_sku 100% 有值 ⇒ 这一档永远配不上，去掉它不改变结果。
--
--   ② **把「数据来源平台」当「销售渠道」做 join**
--      积压行的 platform_code 恒为 'miaoshou'（**数据来源是妙手 ERP**），
--      订单行的 platform_code 是 'shopee' / 'tiktok'（**销售渠道**）。
--      原视图 `b.platform_code = m.platform_code` 拿「来源」比「渠道」⇒ 恒不相等 ⇒ 恒 0 行。
--      库存是**店铺的库存**，妙手只是管库存的系统；渠道属于订单侧。
--      修法：join 只按 SKU 走，并保留一条**兜底规则**——
--            积压行若来自某个销售渠道（platform_code 出现在订单平台集合里），
--            仍只与该渠道的订单配对；来自 ERP 的积压行（平台不在订单集合里）
--            与所有渠道的订单按 SKU 配对。
--
-- 改完实测：join 命中 418 个积压 SKU，视图从 0 行变成按月 × 渠道 × 店铺出榜单。
-- 选行规则（LATERAL + DISTINCT ON + NOT EXISTS + age_days >= 30）与输出列保持不变。
CREATE OR REPLACE VIEW api.clearance_ranking_module AS
-- The previous implementation selected mart.inventory_backlog_base rows.
-- This view keeps compatibility fields while exposing monthly shop rankings.
WITH order_months AS MATERIALIZED (
    SELECT
        date_trunc('month', o.metric_date)::date AS ranking_month,
        o.platform_code,
        -- SKU 口径：与 backlog_rows **逐字相同**（P7 修复 ①）
        COALESCE(NULLIF(BTRIM(o.platform_sku), ''), NULLIF(BTRIM(o.product_sku), ''),
                 NULLIF(BTRIM(o.product_id), '')) AS sku_key,
        o.shop_id,
        COALESCE(o.paid_amount, o.sales_amount, 0) AS sales_amount,
        COALESCE(o.product_quantity, 0)::numeric AS sales_quantity
    FROM semantic.fact_orders_atomic o
    WHERE o.metric_date IS NOT NULL
),
order_platforms AS MATERIALIZED (
    -- 订单侧出现过的平台集合（销售渠道）。用来判断某个积压行的 platform_code
    -- 是「销售渠道」还是「ERP 数据来源」，见 backlog_rows 的注释。
    --
    -- ⚠️ 必须从 **order_months** 派生，不能再扫一遍 semantic.fact_orders_atomic：
    --    原子视图里每行都要跑一次店铺别名解析（33265 次），
    --    多扫一遍就是 **+24.4 秒**（实测 69.2s → 45s 级别的关键一笔）。
    SELECT DISTINCT platform_code
    FROM order_months
    WHERE platform_code IS NOT NULL
),
order_sku_month AS MATERIALIZED (
    -- LATERAL 的驱动行去重：同一 (月份, 平台, SKU) 只算一次，
    -- 选行结果与逐订单行重复计算完全一致。
    SELECT DISTINCT
        ranking_month,
        platform_code,
        sku_key
    FROM order_months
    WHERE sku_key IS NOT NULL
),
backlog_rows AS MATERIALIZED (
    -- 物化：原来在 LATERAL 里被逐条订单行重复计算
    SELECT
        b.platform_code,
        -- SKU 口径：与 order_months **逐字相同**（P7 修复 ①）
        COALESCE(NULLIF(BTRIM(b.platform_sku), ''), NULLIF(BTRIM(b.product_sku), ''),
                 NULLIF(BTRIM(b.product_id), '')) AS sku_key,
        b.snapshot_date,
        COALESCE(b.days_since_restock, 0) AS age_days,
        b.inventory_value,
        -- 这个积压行是不是来自某个**销售渠道**（而不是 ERP 数据来源）。
        -- 提前算好：放在 LATERAL 里逐行判断要多花 25 秒（49.9s → 76.4s）。
        EXISTS (
            SELECT 1
            FROM order_platforms op
            WHERE op.platform_code = b.platform_code
        ) AS from_sales_channel
    FROM mart.inventory_backlog_base b
),
stagnant_before_month AS (
    -- DISTINCT ON 的键 = 驱动行侧的平台 + SKU + 月份。
    -- 平台取**订单侧**的平台（销售渠道），积压侧不再参与（P7 修复 ②）。
    SELECT DISTINCT ON (m.platform_code, m.sku_key, m.ranking_month)
        m.ranking_month,
        m.platform_code,
        m.sku_key,
        -- 2026-10-24：滞销口径换成「距上次进货时长」（stock_changed_at 派生）
        h.age_days,
        h.inventory_value
    FROM order_sku_month m
    JOIN LATERAL (
        SELECT
            b.platform_code,
            b.sku_key,
            b.snapshot_date,
            b.age_days,
            b.inventory_value
        FROM backlog_rows b
        WHERE b.sku_key = m.sku_key
          -- 平台规则（P7 修复 ②）：
          --   - 积压行来自 ERP（平台不在订单平台集合里）⇒ 与任何渠道的订单按 SKU 配对；
          --   - 积压行来自某个销售渠道 ⇒ 只与该渠道的订单配对。
          AND (
                b.platform_code = m.platform_code
             OR NOT b.from_sales_channel
          )
          AND (b.snapshot_date < m.ranking_month
               OR NOT EXISTS (
                    SELECT 1
                    FROM backlog_rows prior
                    WHERE prior.platform_code = b.platform_code
                      AND prior.sku_key = b.sku_key
                      AND prior.snapshot_date < m.ranking_month
               ))
        ORDER BY (b.snapshot_date < m.ranking_month) DESC, b.snapshot_date DESC
        LIMIT 1
    ) h
      ON h.sku_key = m.sku_key
     AND h.age_days >= 30
    ORDER BY m.platform_code, m.sku_key, m.ranking_month, h.snapshot_date DESC
),
shop_month AS (
    SELECT
        o.ranking_month,
        o.platform_code,
        o.shop_id,
        COALESCE(o.shop_id, 'unknown') AS shop_name,
        SUM(o.sales_amount) AS clearance_amount,
        SUM(o.sales_quantity) AS clearance_quantity,
        COUNT(DISTINCT o.sku_key) AS stagnant_sku_count,
        MAX(st.age_days) AS max_stagnant_age_days
    FROM order_months o
    JOIN stagnant_before_month st
      ON st.ranking_month = o.ranking_month
     AND st.platform_code = o.platform_code
     AND st.sku_key = o.sku_key
    GROUP BY o.ranking_month, o.platform_code, o.shop_id
)
SELECT
    ranking_month,
    platform_code,
    shop_id,
    shop_name,
    clearance_amount,
    clearance_quantity,
    stagnant_sku_count,
    max_stagnant_age_days,
    -- 2026-10-24：DOS 已降级为参考值，不再出现在这个视图里
    NULL::numeric AS estimated_turnover_days,
    NULL::numeric AS daily_avg_sales,
    NULL::integer AS stagnant_snapshot_count,
    max_stagnant_age_days AS estimated_stagnant_days,
    CASE
        WHEN max_stagnant_age_days >= 180 THEN 'high'
        WHEN max_stagnant_age_days >= 90 THEN 'medium'
        ELSE 'low'
    END AS risk_level,
    clearance_amount AS inventory_value,
    NULL::text AS platform_sku,
    NULL::text AS product_sku,
    NULL::text AS product_name,
    clearance_amount AS clearance_priority_score,
    ROW_NUMBER() OVER (
        PARTITION BY ranking_month
        ORDER BY clearance_amount DESC, clearance_quantity DESC, shop_name ASC
    ) AS rank,
    clearance_amount AS total_sales,
    clearance_quantity AS total_orders
FROM shop_month;
