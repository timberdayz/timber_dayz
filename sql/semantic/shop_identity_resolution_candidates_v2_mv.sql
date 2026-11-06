CREATE SCHEMA IF NOT EXISTS semantic;

-- ---------------------------------------------------------------------------
-- 店铺身份解析候选集（物化）
--
-- 为什么要有这一层
-- ----------------
-- `semantic.shop_identity_resolution_candidates` 的候选集只有 **136 行**
-- （core.shop_accounts 52 行 + core.shop_account_aliases 21 行派生），
-- 但它是**普通视图** —— 每次被引用都会把 CTE 展开、把 `regexp_replace` 之类
-- 的规范化表达式**重算一遍**。
--
-- 而订单/流量原子层是**每行**都要做一次身份解析（LEFT JOIN LATERAL）。
-- 生产实测（2026-11-04，EXPLAIN ANALYZE 全量重算 38,607 行）：
--
--     Execution Time: 118974.907 ms   （≈ 119 秒）
--
-- 计划里两个节点吃掉了绝大部分时间：
--
--     ->  Unique (actual time=1.430..1.430 rows=1 loops=38607)      ≈ 55 秒
--           ->  Sort ... -> Subquery Scan on identity_rows_1
--     ->  Seq Scan on shop_account_aliases (actual time=0.009..0.019 rows=2
--                                            loops=1482412)          ≈ 28 秒
--
-- 也就是：**每一行订单事实，都把 136 行候选集重新算一遍并排序** ——
-- 38,607 行 × 38 次别名表扫描 = 148 万次。
-- 这是典型的 N+1：候选集是**几乎不变的小表**，却被当成**逐行计算的表达式**。
--
-- 物化之后，候选集变成**一张 136 行的表**，LATERAL 变成索引扫描，
-- 重算成本从「分钟级」降到「秒级」。
--
-- 下游是 `semantic.fact_orders_atomic` / `fact_analytics_atomic`（两个**普通**
-- 视图），它们的正文改为读这个副本。
-- `fact_orders_monthly_atomic_mv` / `fact_analytics_monthly_atomic_mv` 是**既有**
-- 物化视图的完整定义（`DROP ... CASCADE` + `CREATE`），改了要在生产重建它们
-- ⇒ 有风险 ⇒ **保持不动**，它们继续读正本，既有行为不变。
--
-- 正文为什么是**自包含**的一份定义（而不是 `SELECT * FROM` 正本）
-- -------------------------------------------------------------------
-- 两个原因：
-- 1. **正本在不同环境里列数不同** —— 生产上是 8 列（含
--    `identity_shop_region`，区域消歧那套逻辑后来才加的），而全新库的
--    20260805 schema baseline 建的是 **7 列旧版**（`shop_region` 列是
--    20261101 迁移才加的）。副本引用正本 ⇒ 全新库根本建不出 8 列副本。
-- 2. 引用正本 = 副本依赖正本，刷新语义绕一圈。
--
-- 所以这里**手抄一份**定义。副本与正本必须保持同构 ——
-- `backend/tests/data_pipeline/test_identity_candidates_materialization.py`
-- 守着两处最容易漂移的地方（4 路 UNION 的分支数、区域维度列），迁移
-- `20261105` 还会在生产上比**内容指纹**（行数 + 全量 md5），不一致直接回滚。
--
-- 为什么叫 v2
-- -----------
-- 2026-08-05 的 schema baseline 里已经有一个
-- `semantic.shop_identity_resolution_candidates_mv`，但它是**旧版候选集**
-- （只有 7 列，缺 `identity_shop_region` —— 区域匹配那套逻辑是后来加的）。
-- 直接拿它当数据源会让原子层建视图直接报错
-- （`column c.identity_shop_region does not exist`）。
-- 那个 v1 没有被任何对象引用，属于历史遗留，本迁移会把它删掉。
--
-- 刷新顺序（refresh_registry.PIPELINE_DEPENDENCIES 强制）：
--     semantic.shop_identity_resolution_candidates_v2_mv   （本文件，正本）
--       → semantic.shop_identity_resolution_candidates    （转发视图）
--         → 4 个原子层视图 → 物化副本 → 看板消费方
--
-- 刷新成本：136 行，**毫秒级** ⇒ 可以挂在每一次数据刷新链路上，
-- 不会像订单原子层那样把刷新窗口撑到分钟级。
--
-- 关于 DROP ... CASCADE
-- ---------------------
-- 本文件用「存在则 REFRESH（原地刷新）/ 不存在则 CREATE」，
-- **绝不 DROP ... CASCADE** —— CASCADE 会连带删掉下游对象，
-- 而下游里存在**不是 refresh registry 可重建目标**的对象。
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF to_regclass('semantic.shop_identity_resolution_candidates_v2_mv') IS NULL THEN
        EXECUTE $mv$
            CREATE MATERIALIZED VIEW semantic.shop_identity_resolution_candidates_v2_mv AS
            WITH active_shop_accounts AS (
                SELECT
                    sa.id AS shop_account_pk,
                    LOWER(COALESCE(sa.platform, '')) AS platform_code,
                    NULLIF(TRIM(COALESCE(sa.shop_account_id, '')), '') AS resolved_shop_account_id,
                    NULLIF(TRIM(COALESCE(sa.platform_shop_id, '')), '') AS candidate_platform_shop_id,
                    NULLIF(TRIM(COALESCE(sa.store_name, '')), '') AS candidate_store_label,
                    -- 店铺自身的区域（大写，如 MY / PH / SG）；NULL = 不限区域
                    NULLIF(TRIM(COALESCE(sa.shop_region, '')), '') AS candidate_shop_region,
                    COALESCE(
                        NULLIF(TRIM(COALESCE(sa.platform_shop_id, '')), ''),
                        NULLIF(TRIM(COALESCE(sa.shop_account_id, '')), ''),
                        sa.id::text
                    ) AS resolved_shop_id
                FROM core.shop_accounts sa
                -- [*] 2026-11-06: 与正本同步 —— 候选池只收「在营经营店」
                --     (enabled IS TRUE AND business_role = 'operating_store')。
                WHERE sa.enabled IS TRUE
                  AND sa.business_role = 'operating_store'
            ),
            identity_rows AS (
                SELECT
                    platform_code,
                    resolved_shop_id,
                    resolved_shop_account_id,
                    'platform_shop_id'::varchar AS resolution_method,
                    2 AS resolution_priority,
                    LOWER(candidate_platform_shop_id) AS identity_value_normalized,
                    candidate_platform_shop_id AS identity_source_value,
                    candidate_shop_region AS identity_shop_region
                FROM active_shop_accounts
                WHERE candidate_platform_shop_id IS NOT NULL

                UNION ALL

                SELECT
                    platform_code,
                    resolved_shop_id,
                    resolved_shop_account_id,
                    'shop_account_id'::varchar AS resolution_method,
                    1 AS resolution_priority,
                    LOWER(resolved_shop_account_id) AS identity_value_normalized,
                    resolved_shop_account_id AS identity_source_value,
                    candidate_shop_region AS identity_shop_region
                FROM active_shop_accounts
                WHERE resolved_shop_account_id IS NOT NULL

                UNION ALL

                SELECT
                    asa.platform_code,
                    asa.resolved_shop_id,
                    asa.resolved_shop_account_id,
                    'alias_match'::varchar AS resolution_method,
                    3 AS resolution_priority,
                    LOWER(TRIM(saa.alias_normalized)) AS identity_value_normalized,
                    saa.alias_value AS identity_source_value,
                    -- 别名自己的区域（第一批 Task 5 新增列）；NULL = 不限区域
                    NULLIF(TRIM(COALESCE(saa.shop_region, '')), '') AS identity_shop_region
                FROM active_shop_accounts asa
                INNER JOIN core.shop_account_aliases saa
                  ON saa.shop_account_id = asa.shop_account_pk
                 AND saa.is_active = TRUE
                WHERE NULLIF(TRIM(COALESCE(saa.alias_normalized, '')), '') IS NOT NULL
                  -- [*] 与正本同步: 别名这一路不得认领任何账号的平台店铺编号
                  --     (自别名 / 跨账号认领) —— 否则同一串身份值指向两个账号,
                  --     候选数变 2, 整行落 unknown。
                  AND NOT EXISTS (
                        SELECT 1
                        FROM core.shop_accounts alias_owner
                        WHERE alias_owner.enabled IS TRUE
                          AND alias_owner.business_role = 'operating_store'
                          AND LOWER(NULLIF(TRIM(COALESCE(alias_owner.platform_shop_id, '')), ''))
                              = LOWER(TRIM(COALESCE(saa.alias_normalized, '')))
                    )

                UNION ALL

                SELECT
                    platform_code,
                    resolved_shop_id,
                    resolved_shop_account_id,
                    'store_name_match'::varchar AS resolution_method,
                    4 AS resolution_priority,
                    REGEXP_REPLACE(
                        LOWER(
                            TRIM(BOTH FROM REGEXP_REPLACE(
                                TRIM(BOTH FROM COALESCE(active_shop_accounts.candidate_store_label, '')),
                                '^(shopee|tiktok\s*shop|tiktok|tk|miaoshou|amazon|lazada)\s*',
                                '',
                                'i'
                            ))
                        ),
                        '[\s_()/-]+',
                        '',
                        'g'
                    ) AS identity_value_normalized,
                    candidate_store_label AS identity_source_value,
                    candidate_shop_region AS identity_shop_region
                FROM active_shop_accounts
                WHERE candidate_store_label IS NOT NULL
            )
            SELECT
                platform_code,
                identity_value_normalized,
                identity_source_value,
                resolved_shop_id,
                resolved_shop_account_id,
                resolution_method,
                resolution_priority,
                identity_shop_region
            FROM identity_rows
            WHERE NULLIF(TRIM(COALESCE(identity_value_normalized, '')), '') IS NOT NULL
        $mv$;
    ELSE
        EXECUTE 'REFRESH MATERIALIZED VIEW semantic.shop_identity_resolution_candidates_v2_mv';
    END IF;
END
$$;

-- 原子层 LATERAL 的过滤模式：(platform_code, identity_value_normalized)
CREATE INDEX IF NOT EXISTS ix_shop_identity_candidates_v2_mv_platform_identity
ON semantic.shop_identity_resolution_candidates_v2_mv (platform_code, identity_value_normalized);

-- 「取最优候选」用：再按优先级、店号排
CREATE INDEX IF NOT EXISTS ix_shop_identity_candidates_v2_mv_platform_identity_priority
ON semantic.shop_identity_resolution_candidates_v2_mv (platform_code, identity_value_normalized, resolution_priority);

CREATE INDEX IF NOT EXISTS ix_shop_identity_candidates_v2_mv_platform_identity_priority_shop
ON semantic.shop_identity_resolution_candidates_v2_mv (platform_code, identity_value_normalized, resolution_priority, resolved_shop_id);
