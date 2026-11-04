CREATE SCHEMA IF NOT EXISTS semantic;

-- ---------------------------------------------------------------------------
-- 订单事实原子层（物化）
--
-- 为什么要有这一层：
--   `semantic.fact_orders_atomic` 是**普通视图**，每行都要跑一次店铺别名解析
--   （LEFT JOIN LATERAL → semantic.shop_identity_resolution_candidates）。
--   生产实测：EXPLAIN SELECT count(*) FROM mart.shop_day_kpi
--             WHERE period_date = '2026-09-15'  →  20.2 秒。
--   根因：`metric_date` 过滤无法下推到去重窗口（`ROW_NUMBER() OVER
--   (PARTITION BY platform_code, shop_id, data_hash ...)`）之下，于是 9 张
--   B 类订单表被全量扫描 + 逐行 JSON 解析 + 逐行身份解析，每次请求都重算一遍。
--
-- 为什么**物化整个原子视图**，而不是按粒度各建一个 MV：
--   1. **口径零变化**。物化视图的正文就是普通视图的正文（SELECT *），
--      同一份定义、同一套去重、同一套身份解析。物化只改变「什么时候算」，
--      不改变「算什么」。改源重建粒度 MV 会换掉行集合，金额会漂。
--   2. **一个 MV 同时修好 3 个 504 接口**。日/周粒度 KPI 与 B 成本页
--      读的都是这一层；只做日粒度 MV 的话，B 成本页仍然是 20 秒级。
--   3. **刷新成本可接受**。生产实测（2026-11-04）：全量重算一遍原子视图要
--      **114.6 秒**（`SELECT count(*) FROM semantic.fact_orders_atomic`，
--      38,607 行）。它落在离线刷新窗口里，不在用户请求路径上；查询侧从
--      20 秒级降到毫秒级。
--
-- 为什么**不**用 `DROP MATERIALIZED VIEW ... CASCADE`：
--   DROP CASCADE 会连带删掉下游视图。下游里有两个**不是 refresh registry
--   可重建目标**的对象 —— `mart.hr_shop_monthly_profit` 与
--   `mart.inventory_backlog_base_mv` —— 它们只读普通视图，不该被动到；
--   而 `mart.b_cost_shop_month` / `api.b_cost_analysis_order_detail_module`
--   也不在 dashboard bootstrap 的 core 计划里，一旦被 CASCADE 删掉就没人
--   重建 → B 成本页直接挂。
--   「存在则 REFRESH（原地刷新，不删任何东西）/ 不存在则 CREATE」既避开
--   这个问题，也避开「DROP 与重建之间视图短暂消失」的窗口。
--   注：`semantic.fact_orders_atomic` 用的是 `CREATE OR REPLACE VIEW`
--   （不是 DROP），所以普通视图不会被删 → 本 MV 不会被动到 → 一直走 REFRESH。
--
-- 消费方（全部是 registry 里可重建的目标）：
--   mart.shop_day_kpi / mart.shop_week_kpi
--   mart.platform_day_kpi / mart.platform_week_kpi
--   mart.b_cost_shop_month
--   api.b_cost_analysis_order_detail_module
--
-- 刷新顺序（refresh_registry.PIPELINE_DEPENDENCIES 强制）：
--   semantic.shop_identity_resolution_candidates
--     → semantic.fact_orders_atomic          （普通视图，正本）
--       → semantic.fact_orders_atomic_mv     （本文件）
--         → 上面 6 个消费方
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF to_regclass('semantic.fact_orders_atomic_mv') IS NULL THEN
        EXECUTE 'CREATE MATERIALIZED VIEW semantic.fact_orders_atomic_mv AS SELECT * FROM semantic.fact_orders_atomic';
    ELSE
        EXECUTE 'REFRESH MATERIALIZED VIEW semantic.fact_orders_atomic_mv';
    END IF;
END
$$;

-- 日/周粒度 KPI 的过滤模式：(granularity, metric_date) → 平台 → 店铺
CREATE INDEX IF NOT EXISTS ix_fact_orders_atomic_mv_gran_date_platform_shop
ON semantic.fact_orders_atomic_mv (granularity, metric_date, platform_code, shop_id);

-- 去重/身份解析的定位键
CREATE INDEX IF NOT EXISTS ix_fact_orders_atomic_mv_platform_shop_hash
ON semantic.fact_orders_atomic_mv (platform_code, shop_id, data_hash);
