CREATE SCHEMA IF NOT EXISTS semantic;

-- ---------------------------------------------------------------------------
-- 店铺身份解析候选集（物化加速副本）
--
-- 正本 = ``semantic.shop_identity_resolution_candidates``
--       (资产: ``sql/semantic/shop_identity_resolution_candidates.sql``)
--
-- 本文件是它的**物化加速副本**：候选池的口径**只有正本一处定义**，
-- 本文件**不再复写**任何计算逻辑 —— 正文里看不到台账表（``core`` schema
-- 下的店铺账号表与别名表），只声明「从正本取哪几列、按什么顺序」。
--
-- 为什么要有这一层
-- ----------------
-- 正本是**普通视图** —— 每次被引用都会把 CTE 展开、把 ``regexp_replace``
-- 之类的规范化表达式**重算一遍**。
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
-- 也就是：**每一行订单事实，都把候选集重新算一遍并排序** ——
-- 38,607 行 × 38 次别名表扫描 = 148 万次。
-- 这是典型的 N+1：候选集是**几乎不变的小表**，却被当成**逐行计算的表达式**。
--
-- 物化之后，候选集变成**一张小表**，LATERAL 变成索引扫描，
-- 重算成本从「分钟级」降到「秒级」。
--
-- 下游是 ``semantic.fact_orders_atomic`` / ``fact_analytics_atomic``（两个**普通**
-- 视图），它们的正文改为读这个副本。
-- ``fact_orders_monthly_atomic_mv`` / ``fact_analytics_monthly_atomic_mv`` 是**既有**
-- 物化视图的完整定义（``DROP ... CASCADE`` + ``CREATE``），改了要在生产重建它们
-- ⇒ 有风险 ⇒ **保持不动**，它们继续读正本，既有行为不变。
--
-- 口径只有一份（2026-11-11 收回派生层口径）
-- --------------------------------------------------
-- 以前这里**手抄**了一份正本的完整计算逻辑（4 路 UNION + 采集方代号排除），
-- 两边靠人工保持一致 —— 差一点就漂移，而漂移是**静默**的：
-- 副本多一行少一行，看板上只会表现为「某个店没人了」。
--
-- 现在副本**只从正本取数**：
--
--     CREATE MATERIALIZED VIEW semantic.shop_identity_resolution_candidates_v2_mv AS
--     SELECT <显式列清单> FROM semantic.shop_identity_resolution_candidates
--
-- ⇒ 口径的定义**只有正本一处**；副本能装下什么，完全由正本决定。
--
-- 为什么列清单是**显式**的（而不是 ``SELECT *``）
-- --------------------------------------------
-- * ``SELECT *`` 会让副本的列集合/列序**隐式**跟随正本 —— 正本哪天改了列序，
--   副本重建后列序就跟着变；下游（原子层视图、物化副本、看板消费方）
--   的 JOIN 有错位的风险，而这种错位**不报错、只出错数**。
-- * 显式列清单把「副本有哪些列、什么顺序」**写在纸面上**：
--   正本改了列集合而这里没跟上 ⇒ 建副本当场报 ``column does not exist``
--   （fail-closed，**当场报错**），而不是悄悄错位。
--
-- 列清单必须与正本的 SELECT 列表**逐列同名同序**。
-- 守护测试 ``backend/tests/data_pipeline/test_identity_candidates_materialization.py``
-- 会把两边的列清单解析出来逐项比对。
--
-- 刷新语义：存在则 REFRESH / 不存在则 CREATE
-- --------------------------------------------
-- 本文件用「存在则 REFRESH（原地刷新）/ 不存在则 CREATE」，
-- **绝不 DROP ... CASCADE** —— CASCADE 会连带删掉下游对象，
-- 而下游里存在**不是 refresh registry 可重建目标**的对象。
--
-- ⚠️ **口径变更（列数变化）仍然必须 DROP 重建**
-- ------------------------------------------
-- ``REFRESH MATERIALIZED VIEW`` 只重算**数据**，不换**定义**：
-- 正本的列集合变了之后，光 REFRESH 刷出来的还是**旧定义** ⇒ 必须
-- ``DROP MATERIALIZED VIEW``（**不带 CASCADE**）再重建。
-- 迁移 ``20261112_realign_identity_candidates_anchor`` 就是这条路径的样板：
-- 先让依赖副本的对象让开 → DROP（不带 CASCADE）→ 重建 → 换回 → 内容指纹比对。
-- 本次「收回派生层口径」**没有动**这条路径。
--
-- 刷新顺序（refresh_registry.PIPELINE_DEPENDENCIES 强制）：
--     semantic.shop_identity_resolution_candidates        （正本，普通视图）
--       → semantic.shop_identity_resolution_candidates_v2_mv （本文件，物化副本）
--         → 4 个原子层视图 → 物化副本 → 看板消费方
--
-- 刷新成本：候选集只有几十行，**毫秒级** ⇒ 可以挂在每一次数据刷新链路上，
-- 不会像订单原子层那样把刷新窗口撑到分钟级。
--
-- 为什么叫 v2
-- -----------
-- 2026-08-05 的 schema baseline 里已经有一个
-- ``semantic.shop_identity_resolution_candidates_mv``，但它是**旧版候选集**
-- （只有 7 列，缺 ``identity_shop_region`` —— 区域匹配那套逻辑是后来加的）。
-- 直接拿它当数据源会让原子层建视图直接报错
-- （``column c.identity_shop_region does not exist``）。
-- 那个 v1 没有被任何对象引用，属于历史遗留，迁移 ``20261105`` 会把它删掉。
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF to_regclass('semantic.shop_identity_resolution_candidates_v2_mv') IS NULL THEN
        EXECUTE $mv$
            CREATE MATERIALIZED VIEW semantic.shop_identity_resolution_candidates_v2_mv AS
            SELECT
                platform_code,
                identity_value_normalized,
                identity_source_value,
                resolved_shop_id,
                resolved_shop_account_id,
                resolution_method,
                resolution_priority,
                identity_shop_region
            FROM semantic.shop_identity_resolution_candidates
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
