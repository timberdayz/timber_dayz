CREATE SCHEMA IF NOT EXISTS semantic;

-- ---------------------------------------------------------------------------
-- 采集方代号判定函数（本文件自带的**前置**，迁移链执行本文件时自举）
--
-- 「采集方代号」= 表示「这批数据来自哪个采集器」的标识（``xihong`` /
-- ``miaoshou_real_001`` / ``unknown`` / ``none`` / 空串）——
-- **不是**店铺身份。权威清单:
-- ``modules/core/fact_identity_columns.py::COLLECTION_SOURCE_IDS``;
-- 登记载体: ``core.collection_source_identifiers``
-- （迁移 ``current_schema_20261223_collection_source_identifiers`` 播种）。
--
-- 为什么函数定义**内联在本文件**里（而不是单独一个资产）
-- ----------------------------------------------------------
-- 候选池正本资产会被迁移 ``current_schema_20261112_realign_identity_candidates_anchor``
-- **直接执行**（重建候选池）。若把函数放在另一个独立资产里，
-- 那个资产不在迁移链上 ⇒ 全新库跑迁移链时函数还不存在 ⇒
-- 建视图报 "function semantic.is_collection_source_identifier does not exist"。
-- 内联在文件开头 ⇒ **谁执行本文件, 函数先落地**（``CREATE OR REPLACE`` 幂等）。
--
-- 为什么用函数、而不是在视图里直接 JOIN 那张表
-- --------------------------------------------------
-- 直接 JOIN 会让候选池视图**硬依赖** ``core.collection_source_identifiers``：
--   迁移没跑的环境（老库 / 半迁移库 / 只建表的全新库）建视图会直接失败。
-- 这里用 ``to_regclass`` 保护：表不存在 ⇒ **返回 FALSE**（什么都不剔除）
-- ⇒ 行为与改造前完全一致，视图照常建得起来。
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION semantic.is_collection_source_identifier(p_value TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    IF p_value IS NULL THEN
        RETURN FALSE;
    END IF;

    -- 登记载体还没建（迁移未跑）⇒ 不剔除任何值（与改造前一致），而不是让建视图失败。
    IF to_regclass('core.collection_source_identifiers') IS NULL THEN
        RETURN FALSE;
    END IF;

    RETURN EXISTS (
        SELECT 1
          FROM core.collection_source_identifiers csi
         WHERE csi.is_active
           AND csi.identifier = p_value
    );
END;
$$;

-- Best practice note:
-- Avoid DO/EXECUTE dynamic SQL inside SQL assets. If performance requires materialization,
-- implement it in the Python bootstrap runner, not inside the SQL file.
--
-- ---------------------------------------------------------------------------
-- 锚点优先级（2026-11-06 调整：shop_account_id 升为 priority 1）
-- ---------------------------------------------------------------------------
-- 四路候选的优先级就是「同一个身份值同时命中多路时先听谁的」:
--
--   1. shop_account_id  ← 唯一正确锚点（改名不变、跨平台一致、采集器写不坏）
--   2. platform_shop_id ← 会被采集器污染（把 URL 读到的编号当成主数据）、平台换 ID 就失效
--   3. alias_match      ← 妙手导出订单的「店铺」中文列靠它认身份
--   4. store_name_match ← 兜底
--
-- 调整前 platform_shop_id 排第 1、shop_account_id 排第 2 —— **最不稳的那个排在最前**。
--
-- ⚠️ 这次调整**只动排序, 不动计数**:
--   * 候选数仍是 ``count(DISTINCT c.resolved_shop_id)`` —— 歧义判定完全不变,
--     歧义行照样落 ``unknown``（绝不静默挑一个）;
--   * 变的是「歧义行**声称**自己属于谁」和「身份冲突**报给谁**」——
--     以前歧义行会被 ``platform_shop_id`` 那一路带去**被污染的邻居**,
--     现在由 ``shop_account_id`` 那一路带去**真正当事的账号**。
--
-- ⚠️ ``resolved_shop_id`` 的派生口径 (``platform_shop_id`` > ``shop_account_id`` > ``id``)
--    **保持不变**: 语义层输出的 ``shop_id`` 取的是 ``COALESCE(canonical.platform_shop_id,
--    resolved_shop_id)``, 看板显示名的 JOIN 也是拿它跟 ``core.dim_shops.shop_id`` 对齐 ——
--    改这里的 COALESCE 顺序会让 dim_shops 的键与事实表的键对不上, 显示名整片落空。
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW semantic.shop_identity_resolution_candidates AS
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
    -- [*] 2026-11-06: 候选池只收「在营经营店」。
    --     这一条**不是新口径, 是补一处漏抄的过滤** —— 系统其它每一个环节
    --     (采集挑账号 / 员工绩效 / 探测匹配 / 数据同步清理)都已经过滤了
    --     enabled 与 business_role, 只有语义层候选池漏了。
    --     实测候选池 138 行里 69 行(50%)来自 enabled=false 的停用店,
    --     另有 2 行来自 business_role='collection_source'(采集源, 不是经营店)。
    --     补上之后, 停用店名下的 213 行会落 unknown —— 合计只有 8 个 UV,
    --     对看板数字没有任何贡献。
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
      -- [*] 别名这一路**不得认领任何账号的平台店铺编号**:
      --     自别名（别名值 == 自己的 platform_shop_id）与跨账号认领
      --     （别名值 == 别的账号的 platform_shop_id）会让同一串身份值同时
      --     指向两个账号 ⇒ 候选数变 2 ⇒ 整行落 unknown。
      --     而 platform_shop_id 那一路已经认领了这串值, 别名这一路让开即可
      --     （候选数不变, 归属更准）。
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
  -- [*] 采集方代号**不是店铺身份** ⇒ 不进候选池。
  --     权威清单: modules/core/fact_identity_columns.py::COLLECTION_SOURCE_IDS
  --     判定函数: semantic.is_collection_source_identifier
  --               (登记载体 core.collection_source_identifiers;
  --                表不存在时该函数返回 FALSE ⇒ 本视图照常建得起来)
  --     这条规则以前写在 orders_atomic.sql 的**字面量**里 —— 每条链路各抄一份,
  --     漏抄的那条链路会把采集方代号当成店铺身份(库存链就是如此:
  --     4,111 行全部挂在伪店 'xihong' 上)。
  --     收敛到候选池这一层 ⇒ 所有链路(含未来新增的)自动继承, 不必各写一遍。
  AND NOT semantic.is_collection_source_identifier(
        identity_rows.identity_value_normalized
  );

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
