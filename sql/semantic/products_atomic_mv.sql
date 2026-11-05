CREATE SCHEMA IF NOT EXISTS semantic;

-- ---------------------------------------------------------------------------
-- 商品事实原子层（物化）
--
-- 为什么要有这一层：
--   `semantic.fact_products_atomic` 是**普通视图**，每行都要跑一次店铺别名解析
--   （LEFT JOIN LATERAL → semantic.resolve_shop_identity）。
--   生产实测（2026-11-05，容器内直连）：
--     COPY (SELECT * FROM semantic.fact_products_atomic) TO '/dev/null'
--       → **23.2 秒**（强制全量物化，等价于建这个 MV 的成本）
--     COPY (SELECT * FROM mart.product_day_kpi) TO '/dev/null'
--       → **14.1 秒**（商品日粒度 KPI，含转化率）
--   慢在同一个地方：去重窗口（ROW_NUMBER() OVER (PARTITION BY ... data_hash)）
--   之上做不了日期/粒度下推，于是每次请求都要重做
--   「多表 UNION + 逐行 JSON 解析 + 逐行身份解析」。
--
--   受影响的业务面：`mart.product_day_kpi` 被
--   `backend/domains/business/routers/performance_management.py`（商品经营分析）
--   与 `backend/services/sync_standardization_quality_service.py`（标准化质量核对）
--   读取；前者是给商品运营看的「转化率」页。
--
-- 为什么**物化整个原子视图**，而不是按粒度各建一个 MV：
--   口径零变化。物化视图的正文就是普通视图的正文（SELECT *）——
--   同一份定义、同一套去重、同一套身份解析。物化只改变「什么时候算」，
--   不改变「算什么」。改源重建粒度 MV 会换掉行集合（商品表里有
--   daily/weekly/monthly 三种粒度，商品日 KPI 只取 daily）⇒ 金额会漂。
--
-- 为什么**不**用 `DROP MATERIALIZED VIEW ... CASCADE`：
--   CASCADE 会连带删掉下游。本 MV 的唯一消费方 `mart.product_day_kpi`
--   是 registry 里可重建的目标，但它**不在** dashboard bootstrap 的 core 计划里
--   ⇒ 被 CASCADE 删掉时没人保证重建。
--   「存在则 REFRESH（原地刷新，不删任何东西）/ 不存在则 CREATE」既避开这个
--   问题，也避开「DROP 与重建之间视图短暂消失」的窗口。
--   注：`semantic.fact_products_atomic` 用的是 `CREATE OR REPLACE VIEW`
--   （不是 DROP），所以普通视图不会被删 → 本 MV 不会被动到 → 一直走 REFRESH。
--
-- 消费方：
--   mart.product_day_kpi
--
-- 刷新顺序（refresh_registry.PIPELINE_DEPENDENCIES 强制）：
--   semantic.alias_registry / semantic.shop_identity_resolver
--     → semantic.fact_products_atomic        （普通视图，正本）
--       → semantic.fact_products_atomic_mv   （本文件）
--         → mart.product_day_kpi
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF to_regclass('semantic.fact_products_atomic_mv') IS NULL THEN
        EXECUTE 'CREATE MATERIALIZED VIEW semantic.fact_products_atomic_mv AS SELECT * FROM semantic.fact_products_atomic';
    ELSE
        EXECUTE 'REFRESH MATERIALIZED VIEW semantic.fact_products_atomic_mv';
    END IF;
END
$$;

-- 商品日 KPI 的过滤模式：(granularity, metric_date) → 平台 → 店铺
CREATE INDEX IF NOT EXISTS ix_fact_products_atomic_mv_gran_date_platform_shop
ON semantic.fact_products_atomic_mv (granularity, metric_date, platform_code, shop_id);

-- 去重/身份解析的定位键
CREATE INDEX IF NOT EXISTS ix_fact_products_atomic_mv_platform_shop_hash
ON semantic.fact_products_atomic_mv (platform_code, shop_id, data_hash);
