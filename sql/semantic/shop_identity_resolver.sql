CREATE SCHEMA IF NOT EXISTS semantic;

-- 全站唯一的「原始店铺标识 → 规范店铺键」解析入口。
--
-- 为什么要有这个函数
-- ------------------
-- 语义层有 5 条链路：orders / analytics / products / services / inventory。
-- 以前只有 orders 与 analytics 做了身份解析（每行跑一次 LEFT JOIN LATERAL，
-- 逻辑在两个文件里各抄了一份）；products / services / inventory **完全没解析**，
-- 直接把采集文件里的原始 shop_id 透传出去 ⇒
--   - 同一个店在不同链路里是三种键（平台店铺ID / 业务店铺ID / 原始店名 / 占位键）
--   - 库存链路的 4,111 行全部挂在占位键 'xihong' 上 ⇒ 库存看板按店拆不开
--
-- 这个函数把「候选计数 + 区域两层消歧 + 取最优候选」收敛成一份，
-- 三条未解析链路直接调用，口径与 orders_atomic 完全一致。
--
-- 口径与 orders_atomic 逐条对齐（改一处必须同时改另一处）
-- ------------------------------------------------------
-- 1. 候选集：semantic.shop_identity_resolution_candidates_v2_mv
--    （正本 = semantic.shop_identity_resolution_candidates，物化副本内容指纹守护）
-- 2. 区域两层：层 1 = 区域精确匹配；层 2 = 完整候选集（层 1 为空时的兜底）。
--    写成「并集」会凭空制造新的 unknown。
-- 3. 候选数按 **去重后的 resolved_shop_id** 算，不是按候选行数
--    （一个账号会同时命中 platform_shop_id / shop_account_id / 店名三路）。
--
-- 返回值
-- ------
--   resolved_shop_id          解析出的规范店铺键（候选唯一时）
--   resolved_shop_account_id  解析出的店铺账号 ID
--   candidate_count           去重后的候选店铺数（>1 = 有歧义，不许挑一个）
--   resolution_method         命中的解析方式（platform_shop_id / shop_account_id /
--                             alias_match / store_name_match）
--
-- ⚠️ 调用方**不能**无条件用 resolved_shop_id 覆盖原值：
--    候选为 0（这个店在本系统里就没有账号）时必须保留原始键 ——
--    覆盖成 'unknown' 等于把「看得见的原始标识」抹成「看不出所以然」。
--    候选 > 1（有歧义）才必须落 'unknown'，因为挑一个就是猜。
CREATE OR REPLACE FUNCTION semantic.resolve_shop_identity(
    p_platform_code TEXT,
    p_candidate_values TEXT[],
    p_source_region TEXT DEFAULT NULL
)
RETURNS TABLE (
    resolved_shop_id TEXT,
    resolved_shop_account_id TEXT,
    candidate_count INT,
    resolution_method TEXT
)
LANGUAGE sql
STABLE
AS $$
    WITH scoped AS (
        SELECT c.resolved_shop_id,
               c.resolved_shop_account_id,
               c.resolution_method,
               c.resolution_priority,
               c.identity_source_value
          FROM semantic.shop_identity_resolution_candidates_v2_mv c
         WHERE c.platform_code = lower(COALESCE(p_platform_code, ''))
           AND c.identity_value_normalized = ANY (COALESCE(p_candidate_values, ARRAY[]::text[]))
           AND (
                 (
                     c.identity_shop_region IS NOT NULL
                     AND p_source_region IS NOT NULL
                     AND c.identity_shop_region = p_source_region
                 )
                 OR NOT EXISTS (
                     SELECT 1
                     FROM semantic.shop_identity_resolution_candidates_v2_mv c_exact
                     WHERE c_exact.platform_code = lower(COALESCE(p_platform_code, ''))
                       AND c_exact.identity_value_normalized = ANY (COALESCE(p_candidate_values, ARRAY[]::text[]))
                       AND c_exact.identity_shop_region IS NOT NULL
                       AND p_source_region IS NOT NULL
                       AND c_exact.identity_shop_region = p_source_region
                 )
           )
    ),
    agg AS (
        SELECT count(DISTINCT s.resolved_shop_id)::int AS cnt
          FROM scoped s
    ),
    best AS (
        SELECT DISTINCT ON (s.resolved_shop_id)
               s.resolved_shop_id,
               s.resolved_shop_account_id,
               s.resolution_method,
               s.resolution_priority,
               s.identity_source_value
          FROM scoped s
         ORDER BY s.resolved_shop_id, s.resolution_priority, s.resolution_method, s.identity_source_value
    )
    SELECT b.resolved_shop_id,
           b.resolved_shop_account_id,
           a.cnt,
           b.resolution_method
      FROM agg a
      LEFT JOIN LATERAL (
          SELECT b1.resolved_shop_id,
                 b1.resolved_shop_account_id,
                 b1.resolution_method
            FROM best b1
           ORDER BY b1.resolution_priority, b1.resolved_shop_id
           LIMIT 1
      ) b ON TRUE;
$$;
