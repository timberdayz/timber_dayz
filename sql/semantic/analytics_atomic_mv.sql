CREATE SCHEMA IF NOT EXISTS semantic;

-- ---------------------------------------------------------------------------
-- 流量事实原子层（物化）
--
-- 与 `sql/semantic/orders_atomic_mv.sql` 同一个套路：`semantic.fact_analytics_atomic`
-- 是普通视图，每行跑一次店铺别名解析；`mart.shop_day_kpi` / `mart.shop_week_kpi` /
-- `mart.platform_day_kpi` / `mart.platform_week_kpi` 都同时读订单层和流量层，
-- 只物化订单层的话，这 4 个视图照样是 20 秒级。
--
-- 生产实测规模（2026-11-04）：流量事实合计 4,431 行
--   shopee daily 10 / shopee monthly 2,993 / tiktok daily 72 / tiktok monthly 1,356
--   weekly 与 miaoshou 均为 0 行 —— 体量小，物化几乎零成本。
--
-- 口径零变化：正文就是普通视图的正文（SELECT *），只改「什么时候算」。
--
-- 「存在则 REFRESH / 不存在则 CREATE」的理由见 orders_atomic_mv.sql 的注释：
-- 不用 DROP ... CASCADE，避免连带删掉下游、避免视图短暂消失的窗口。
--
-- ⚠️ `sql/semantic/analytics_atomic.sql` 开头是 `DROP VIEW ... CASCADE`，
--    重建普通视图时本 MV 会被连带删掉 —— 这是预期的：下一次执行本文件时
--    走 CREATE 分支重建（4,431 行，几百毫秒），再由 refresh pipeline 按
--    依赖顺序重建 4 个日/周 KPI 视图。与既有月度 MV 是同一套机制。
--
-- 刷新顺序（refresh_registry.PIPELINE_DEPENDENCIES 强制）：
--   semantic.shop_identity_resolution_candidates
--     → semantic.fact_analytics_atomic        （普通视图，正本）
--       → semantic.fact_analytics_atomic_mv   （本文件）
--         → 4 个日/周 KPI 视图
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF to_regclass('semantic.fact_analytics_atomic_mv') IS NULL THEN
        EXECUTE 'CREATE MATERIALIZED VIEW semantic.fact_analytics_atomic_mv AS SELECT * FROM semantic.fact_analytics_atomic';
    ELSE
        EXECUTE 'REFRESH MATERIALIZED VIEW semantic.fact_analytics_atomic_mv';
    END IF;
END
$$;

-- 日/周粒度 KPI 的过滤模式：(granularity, metric_date) → 平台 → 店铺
CREATE INDEX IF NOT EXISTS ix_fact_analytics_atomic_mv_gran_date_platform_shop
ON semantic.fact_analytics_atomic_mv (granularity, metric_date, platform_code, shop_id);

-- 去重/身份解析的定位键
CREATE INDEX IF NOT EXISTS ix_fact_analytics_atomic_mv_platform_shop_hash
ON semantic.fact_analytics_atomic_mv (platform_code, shop_id, data_hash);
