CREATE SCHEMA IF NOT EXISTS semantic;

-- ---------------------------------------------------------------------------
-- 库存事实语义层（物化副本）
--
-- 与 `sql/semantic/analytics_atomic_mv.sql` 同一个套路：
-- `semantic.fact_inventory_snapshot` 是普通视图，每一行都要跑一次
-- `semantic.is_collection_source_identifier()` / `semantic.resolve_warehouse_code()`
-- （两张小对照表被反复扫），候选池与 `scoped` CTE 也会被逐行重算。
--
-- 生产实测（3855 行，2026-11-14）：
--   直接读三张 b_class 底表          → 4.4 ms
--   读 semantic.fact_inventory_snapshot → 197 ms   （45 倍）
--
-- 口径零变化：正文就是普通视图的正文（SELECT *），只改「什么时候算」。
--
-- 「存在则 REFRESH / 不存在则 CREATE」的理由见 orders_atomic_mv.sql 的注释：
-- 不用 DROP ... CASCADE，避免连带删掉下游、避免视图短暂消失的窗口。
--
-- ⚠️ 形状守卫（本文件与其它 MV 资产唯一的差别，理由见下）
-- `sql/semantic/inventory_snapshot.sql` 用的是 `CREATE OR REPLACE VIEW`
-- （**不是** DROP ... CASCADE）⇒ 正本加了列时**本副本不会被连带删掉**，
-- 而 `REFRESH MATERIALIZED VIEW` **不会新增列** ⇒ 副本会静默少一列。
-- ⇒ 每次执行本文件时比一次列集，不一致就**报错停下**（fail-closed），
--    而不是悄悄丢列。修法：手工删掉本副本后重跑刷新计划
--    （副本会按新列集重建；被连带删掉的下游视图由刷新计划一并重建）。
--
-- 刷新顺序（refresh_registry.PIPELINE_DEPENDENCIES 强制）：
--   semantic.fact_inventory_snapshot        （普通视图，正本）
--     → semantic.fact_inventory_snapshot_mv  （本文件）
--       → mart.inventory_snapshot_history / mart.inventory_current
--         → mart.inventory_state（状态层由 InventoryStateRefreshService 写入）
-- ---------------------------------------------------------------------------

DO $$
DECLARE
    v_view_columns text;
    v_mv_columns text;
BEGIN
    IF to_regclass('semantic.fact_inventory_snapshot_mv') IS NULL THEN
        EXECUTE 'CREATE MATERIALIZED VIEW semantic.fact_inventory_snapshot_mv AS SELECT * FROM semantic.fact_inventory_snapshot';
    ELSE
        -- 形状守卫：正本视图的列集与副本不一致时，REFRESH 不会新增列 ⇒ 会静默丢列。
        -- fail-closed：报错停下，不带着旧形状继续刷。
        --
        -- ⚠️ 必须用 ``pg_attribute``，**不能**用 ``information_schema.columns``：
        --    information_schema 只列 relkind ∈ {r,v,f,p}，**不含物化视图(relkind='m')**
        --    ⇒ 副本的列集永远取不到(NULL) ⇒ 守卫会把「一致」也判成「不一致」。
        SELECT string_agg(attname, ',' ORDER BY attnum)
          INTO v_view_columns
          FROM pg_attribute
         WHERE attrelid = to_regclass('semantic.fact_inventory_snapshot')
           AND attnum > 0
           AND NOT attisdropped;
        SELECT string_agg(attname, ',' ORDER BY attnum)
          INTO v_mv_columns
          FROM pg_attribute
         WHERE attrelid = to_regclass('semantic.fact_inventory_snapshot_mv')
           AND attnum > 0
           AND NOT attisdropped;
        IF v_view_columns IS DISTINCT FROM v_mv_columns THEN
            RAISE EXCEPTION
                'semantic.fact_inventory_snapshot_mv 的列集与正本 semantic.fact_inventory_snapshot 不一致：REFRESH 不会新增列，继续刷新会静默丢列。请手工删除该物化视图（连带删掉的下游视图由刷新计划重建）后重跑刷新计划。';
        END IF;
        EXECUTE 'REFRESH MATERIALIZED VIEW semantic.fact_inventory_snapshot_mv';
    END IF;
END
$$;

-- 常用过滤模式：(granularity, metric_date) → 平台 → 店铺
CREATE INDEX IF NOT EXISTS ix_fact_inventory_snapshot_mv_gran_date_platform_shop
ON semantic.fact_inventory_snapshot_mv (granularity, metric_date, platform_code, shop_id);

-- 去重/身份解析的定位键
CREATE INDEX IF NOT EXISTS ix_fact_inventory_snapshot_mv_platform_shop_hash
ON semantic.fact_inventory_snapshot_mv (platform_code, shop_id, data_hash);
