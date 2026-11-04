CREATE SCHEMA IF NOT EXISTS semantic;

-- ---------------------------------------------------------------------------
-- 店铺身份解析候选集（转发视图）
--
-- **正本已经搬到物化副本**：
-- `sql/semantic/shop_identity_resolution_candidates_v2_mv.sql`
--
-- 为什么转发
-- --------
-- 这个候选集只有 136 行，却会被订单/流量原子层**逐行**做身份解析
-- （LEFT JOIN LATERAL）。它是普通视图时，每一行订单事实都会把候选集
-- 的 CTE 展开、把规范化表达式重算一遍 —— 生产实测全量重算 38,607 行要
-- **119 秒**，计划里 `shop_account_aliases` 被扫了 **148 万次**。
--
-- 物化之后，候选集变成一张 136 行的表，重算成本降到秒级。
--
-- **本文件只做转发**，所以 4 个下游原子层视图
-- （`semantic.fact_orders_atomic` / `fact_analytics_atomic` /
-- `fact_orders_monthly_atomic_mv` / `fact_analytics_monthly_atomic_mv`）
-- 的正文**一个字都不用改** ⇒ 口径零变化、不需要重建、不需要重新验证金额。
--
-- 依赖方向（不能反，否则循环依赖）：
--     semantic.shop_identity_resolution_candidates_v2_mv   （正本，从 core 表算）
--       → semantic.shop_identity_resolution_candidates    （本文件，转发）
--         → 4 个原子层视图
--
-- 执行顺序要求：**v2_mv 必须先存在**，否则本文件会失败。
-- 迁移 `20261106_materialize_identity_candidates` 与
-- `refresh_registry.PIPELINE_DEPENDENCIES` 都强制了这个顺序。
--
-- Best practice note:
-- Avoid DO/EXECUTE dynamic SQL inside SQL assets. If performance requires materialization,
-- implement it in the Python bootstrap runner, not inside the SQL file.
-- （物化本身放在 v2_mv 资产里，用的是「存在则 REFRESH / 不存在则 CREATE」，
--   与 orders_atomic_mv.sql 同一范式 —— 不 DROP ... CASCADE。）
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW semantic.shop_identity_resolution_candidates AS
SELECT * FROM semantic.shop_identity_resolution_candidates_v2_mv;

CREATE INDEX IF NOT EXISTS ix_shop_accounts_platform_shop_id_lookup
ON core.shop_accounts (
    LOWER(COALESCE(platform, '')),
    LOWER(COALESCE(platform_shop_id, ''))
);

CREATE INDEX IF NOT EXISTS ix_shop_accounts_platform_account_id_lookup
ON core.shop_accounts (
    LOWER(COALESCE(platform, '')),
    LOWER(COALESCE(shop_account_id, ''))
);

CREATE INDEX IF NOT EXISTS ix_shop_account_aliases_platform_alias_lookup
ON core.shop_account_aliases (
    platform,
    LOWER(TRIM(alias_normalized)),
    is_active
);
