CREATE SCHEMA IF NOT EXISTS semantic;

-- Deploy-time bootstrap rebuilds the full dashboard pipeline. Dropping the MV with CASCADE is
-- acceptable here because downstream semantic/mart/api views will be recreated by the runner
-- in dependency order.
DROP MATERIALIZED VIEW IF EXISTS semantic.fact_orders_monthly_atomic_mv CASCADE;

CREATE MATERIALIZED VIEW semantic.fact_orders_monthly_atomic_mv AS
WITH raw_monthly_orders AS MATERIALIZED (
    SELECT
        platform_code, shop_id, data_domain, granularity,
        metric_date, raw_data, data_hash, ingest_timestamp
    FROM b_class.fact_shopee_orders_monthly
    UNION ALL
    SELECT
        platform_code, shop_id, data_domain, granularity,
        metric_date, raw_data, data_hash, ingest_timestamp
    FROM b_class.fact_tiktok_orders_monthly
    UNION ALL
    SELECT
        platform_code, shop_id, data_domain, granularity,
        metric_date, raw_data, data_hash, ingest_timestamp
    FROM b_class.fact_miaoshou_orders_monthly
),
mapped_monthly_orders AS MATERIALIZED (
    SELECT
        metric_date,
        platform_code,
        data_domain,
        granularity,
        NULLIF(TRIM(COALESCE(shop_id, '')), '') AS source_shop_id,
        NULLIF(
            TRIM(
                COALESCE(
                    raw_data->>'店铺',
                    raw_data->>'店铺名',
                    raw_data->>'店铺名称',
                    raw_data->>'store_name',
                    raw_data->>'store_label_raw'
                )
            ),
            ''
        ) AS store_label_raw,
        NULLIF(
            TRIM(
                COALESCE(
                    raw_data->>'platform_shop_id',
                    raw_data->>'平台店铺ID',
                    raw_data->>'店铺ID'
                )
            ),
            ''
        ) AS source_platform_shop_id,
        NULLIF(
            TRIM(
                COALESCE(
                    raw_data->>'shop_account_id',
                    raw_data->>'account_id',
                    raw_data->>'店铺账号ID',
                    raw_data->>'账号ID',
                    raw_data->>'account'
                )
            ),
            ''
        ) AS source_shop_account_id,
        NULLIF(TRIM(COALESCE(raw_data->>'站点', raw_data->>'site')), '') AS source_site,
        COALESCE(
            raw_data->>'订单号',
            raw_data->>'订单ID',
            raw_data->>'订单编号',
            raw_data->>'ID',
            raw_data->>'order_id',
            raw_data->>'Order ID',
            raw_data->>'order_no'
        ) AS order_id,
        COALESCE(
            NULLIF(TRIM(raw_data->>'下单时间'), ''),
            NULLIF(TRIM(raw_data->>'订单创建时间'), ''),
            NULLIF(TRIM(raw_data->>'create_time'), ''),
            NULLIF(TRIM(raw_data->>'order_create_time'), ''),
            NULLIF(TRIM(raw_data->>'order_time'), '')
        ) AS order_time_raw,
        -- ── 取数一律走别名表(单一事实源) ──────────────────────────
        --
        -- 以前这里是手写 COALESCE 链, **兜底会落到裸名列**:
        -- `买家实付金额(RMB)` 缺 → 落到 `买家实付金额`(原币)
        -- `利润(RMB)`       缺 → 落到 `利润`(原币)
        -- 源表里每个金额列都有「原币 + (RMB)」两列, 实测两者均值差约 3 倍
        -- ⇒ 兜底到裸名 = 混币种。
        --
        -- ⇒ 改成走别名表: 别名表**只登 (RMB) 变体** ⇒ 取不到就是 NULL,
        -- 绝不悄悄换成原币。
        semantic.resolve_alias(raw_data, data_domain, 'paid_amount', platform_code, granularity) AS paid_amount_raw,
        semantic.resolve_alias(raw_data, data_domain, 'profit', platform_code, granularity) AS profit_raw,
        -- 列名 ``product_quantity`` / 语义键 ``sales_volume`` —— 同上(见
        -- ``sql/semantic/orders_atomic.sql`` 的同名注释)。
        semantic.resolve_alias(raw_data, data_domain, 'sales_volume', platform_code, granularity) AS product_quantity_raw,
        data_hash,
        ingest_timestamp
    FROM raw_monthly_orders
),
normalized_monthly_orders AS MATERIALIZED (
    SELECT
        COALESCE(
            date_trunc(
                'month',
                CASE
                    WHEN order_time_raw ~ '^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}'
                    THEN to_timestamp(order_time_raw, 'YYYY-MM-DD HH24:MI:SS')
                    WHEN order_time_raw ~ '^\d{4}-\d{2}-\d{2}$'
                    THEN to_date(order_time_raw, 'YYYY-MM-DD')::timestamp
                    ELSE metric_date::timestamp
                END
            )::date,
            date_trunc('month', metric_date)::date
        ) AS metric_date,
        platform_code,
        data_domain,
        granularity,
        source_shop_id,
        store_label_raw,
        source_platform_shop_id,
        source_shop_account_id,
        source_site,
        -- 站点 → 区域码（大写，与 core.shop_accounts.shop_region 比较）。
        -- 8 项映射与 backend/domains/collection/routers/account_alignment.py 的 `site_map` 对齐
        -- （改一侧必须同时改另一侧；两侧 fallback 的大小写**有意**不同：Python 侧小写只用于
        --  生成建议 id，SQL 侧大写才与 shop_region 比较）。
        CASE lower(NULLIF(TRIM(BOTH FROM COALESCE(source_site, '')), ''))
            WHEN '菲律宾' THEN 'PH'
            WHEN '新加坡' THEN 'SG'
            WHEN '马来' THEN 'MY'
            WHEN '马来西亚' THEN 'MY'
            WHEN '泰国' THEN 'TH'
            WHEN '越南' THEN 'VN'
            WHEN '印尼' THEN 'ID'
            WHEN '巴西' THEN 'BR'
            ELSE UPPER(LEFT(NULLIF(TRIM(BOTH FROM COALESCE(source_site, '')), ''), 2))
        END AS source_region,
        order_id,
        CASE
            WHEN paid_amount_raw IS NULL THEN NULL
            ELSE NULLIF(
                REGEXP_REPLACE(
                    REPLACE(REPLACE(REPLACE(REPLACE(paid_amount_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                    '[^0-9.-]',
                    '',
                    'g'
                ),
                ''
            )::numeric
        END AS paid_amount,
        CASE
            WHEN profit_raw IS NULL THEN NULL
            ELSE NULLIF(
                REGEXP_REPLACE(
                    REPLACE(REPLACE(REPLACE(REPLACE(profit_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                    '[^0-9.-]',
                    '',
                    'g'
                ),
                ''
            )::numeric
        END AS profit,
        CASE
            WHEN product_quantity_raw IS NULL THEN NULL
            ELSE NULLIF(
                REGEXP_REPLACE(
                    REPLACE(REPLACE(REPLACE(REPLACE(product_quantity_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                    '[^0-9.-]',
                    '',
                    'g'
                ),
                ''
            )::numeric
        END AS product_quantity,
        LOWER(COALESCE(source_shop_id, '')) AS normalized_source_shop_id,
        LOWER(COALESCE(source_platform_shop_id, '')) AS normalized_source_platform_shop_id,
        LOWER(COALESCE(source_shop_account_id, '')) AS normalized_source_shop_account_id,
        REGEXP_REPLACE(
            REGEXP_REPLACE(
                LOWER(TRIM(COALESCE(source_shop_id, ''))),
                '^(shopee|tiktok\s*shop|tiktok|tk|miaoshou|amazon|lazada)\s*',
                '',
                'i'
            ),
            '[[:space:]_()/-]+',
            '',
            'g'
        ) AS normalized_source_shop_id_compact,
        REGEXP_REPLACE(
            REGEXP_REPLACE(
                LOWER(TRIM(COALESCE(store_label_raw, ''))),
                '^(shopee|tiktok\s*shop|tiktok|tk|miaoshou|amazon|lazada)\s*',
                '',
                'i'
            ),
            '[[:space:]_()/-]+',
            '',
            'g'
        ) AS normalized_store_label_raw,
        data_hash,
        ingest_timestamp
    FROM mapped_monthly_orders
),
prepared_identity_monthly_orders AS MATERIALIZED (
    SELECT
        n.*,
        ARRAY_REMOVE(
            ARRAY[
                n.normalized_source_platform_shop_id,
                n.normalized_source_shop_account_id,
                CASE
                    WHEN n.normalized_source_shop_id NOT IN ('xihong', 'unknown', 'none')
                    THEN n.normalized_source_shop_id
                END,
                CASE
                    WHEN n.normalized_source_shop_id NOT IN ('xihong', 'unknown', 'none')
                    THEN n.normalized_source_shop_id_compact
                END,
                n.normalized_store_label_raw
            ],
            ''
        ) AS normalized_identity_candidates
    FROM normalized_monthly_orders n
),
resolved_monthly_orders AS MATERIALIZED (
    SELECT
        m.metric_date,
        m.platform_code,
        m.data_domain,
        m.granularity,
        CASE
            WHEN resolved.candidate_count = 1
            THEN COALESCE(NULLIF(TRIM(canonical.platform_shop_id), ''), resolved.resolved_shop_id)
            ELSE 'unknown'
        END AS shop_id,
        COALESCE(m.source_shop_id, m.store_label_raw) AS raw_shop_id,
        m.store_label_raw,
        resolved.resolved_shop_account_id,
        CASE
            WHEN resolved.resolved_shop_id IS NOT NULL THEN resolved.resolution_method
            WHEN COALESCE(m.source_platform_shop_id, m.source_shop_account_id, m.store_label_raw, m.source_shop_id) IS NULL THEN 'missing_identity'
            ELSE 'unclaimed_identity'
        END AS resolution_method,
        CASE
            WHEN resolved.resolved_shop_id IS NOT NULL THEN resolved.identity_source_value
            ELSE COALESCE(m.source_platform_shop_id, m.source_shop_account_id, m.store_label_raw, m.source_shop_id)
        END AS identity_source_value,
        CASE
            WHEN resolved.resolved_shop_account_id IS NOT NULL
            THEN COALESCE(NULLIF(TRIM(canonical.platform_shop_id), ''), resolved.resolved_shop_id)
        END AS canonical_shop_id,
        CASE
            WHEN COALESCE(m.source_platform_shop_id, m.source_shop_account_id, m.store_label_raw, m.source_shop_id) IS NULL
            THEN 'missing_identity'
            WHEN resolved.candidate_count = 0
            THEN 'unmatched_shop_label'
            WHEN resolved.candidate_count > 1
            THEN 'ambiguous_shop_label'
            WHEN resolved.resolved_shop_account_id IS NULL
            THEN 'unresolved_shop_account'
            WHEN resolved.resolved_shop_account_id IS NOT NULL AND canonical.shop_account_id IS NULL
            THEN 'unresolved_shop_account'
            WHEN resolved.resolved_shop_account_id IS NOT NULL
             AND LOWER(COALESCE(m.platform_code, '')) IN ('shopee')
             AND NULLIF(TRIM(canonical.platform_shop_id), '') IS NULL
            THEN 'missing_required_platform_shop_id'
            ELSE NULL
        END AS identity_warning_code,
        resolved.candidate_count AS identity_candidate_count,
        resolved.candidate_shop_ids::text AS identity_candidates,
        m.order_id,
        m.paid_amount,
        m.product_quantity,
        m.profit,
        m.data_hash,
        m.ingest_timestamp
    FROM prepared_identity_monthly_orders m
    LEFT JOIN LATERAL (
        SELECT
            agg.candidate_count,
            agg.candidate_shop_ids,
            best.resolved_shop_id,
            best.resolved_shop_account_id,
            best.resolution_method,
            best.resolution_priority,
            best.identity_source_value
        FROM (
            -- ① 计数与候选清单：纯聚合，按去重后的店铺算
            SELECT
                count(DISTINCT c.resolved_shop_id)::int AS candidate_count,
                array_agg(DISTINCT c.resolved_shop_id ORDER BY c.resolved_shop_id) AS candidate_shop_ids
            FROM semantic.shop_identity_resolution_candidates c
            WHERE c.platform_code = lower(COALESCE(m.platform_code, ''))
              AND c.identity_value_normalized = ANY (m.normalized_identity_candidates)
              -- 区域感知匹配：层 1 = 区域精确匹配；层 2 = 完整候选集（层 1 为空时的兜底）。
              -- 写成「并集」会凭空制造新的 unknown，这里必须是「层 1 为空才回落完整候选集」。
              AND (
                    (
                        c.identity_shop_region IS NOT NULL
                        AND m.source_region IS NOT NULL
                        AND c.identity_shop_region = m.source_region
                    )
                    OR NOT EXISTS (
                        SELECT 1
                        FROM semantic.shop_identity_resolution_candidates c_exact
                        WHERE c_exact.platform_code = lower(COALESCE(m.platform_code, ''))
                          AND c_exact.identity_value_normalized = ANY (m.normalized_identity_candidates)
                          AND c_exact.identity_shop_region IS NOT NULL
                          AND m.source_region IS NOT NULL
                          AND c_exact.identity_shop_region = m.source_region
                    )
              )
        ) agg
        LEFT JOIN LATERAL (
            -- ② 最优候选：每个店只保留优先级最高的一行
            SELECT DISTINCT ON (c.resolved_shop_id)
                   c.resolved_shop_id,
                   c.resolved_shop_account_id,
                   c.resolution_method,
                   c.resolution_priority,
                   c.identity_source_value
            FROM semantic.shop_identity_resolution_candidates c
            WHERE c.platform_code = lower(COALESCE(m.platform_code, ''))
              AND c.identity_value_normalized = ANY (m.normalized_identity_candidates)
              -- 与 ① 计数子查询**同一段**区域过滤，否则计数与归属会不一致
              AND (
                    (
                        c.identity_shop_region IS NOT NULL
                        AND m.source_region IS NOT NULL
                        AND c.identity_shop_region = m.source_region
                    )
                    OR NOT EXISTS (
                        SELECT 1
                        FROM semantic.shop_identity_resolution_candidates c_exact
                        WHERE c_exact.platform_code = lower(COALESCE(m.platform_code, ''))
                          AND c_exact.identity_value_normalized = ANY (m.normalized_identity_candidates)
                          AND c_exact.identity_shop_region IS NOT NULL
                          AND m.source_region IS NOT NULL
                          AND c_exact.identity_shop_region = m.source_region
                    )
              )
            ORDER BY c.resolved_shop_id, c.resolution_priority, c.resolution_method, c.identity_source_value
        ) best ON TRUE
        ORDER BY best.resolution_priority, best.resolved_shop_id
        LIMIT 1
    ) resolved ON TRUE
    LEFT JOIN core.shop_accounts canonical
      ON LOWER(COALESCE(canonical.platform, '')) = LOWER(COALESCE(m.platform_code, ''))
     AND canonical.shop_account_id = resolved.resolved_shop_account_id
),
deduplicated_monthly_orders AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY platform_code, COALESCE(shop_id, ''), data_hash
            ORDER BY ingest_timestamp DESC
        ) AS rn
    FROM resolved_monthly_orders
)
SELECT
    metric_date,
    platform_code,
    shop_id,
    raw_shop_id,
    store_label_raw,
    resolved_shop_account_id,
    resolution_method,
    identity_source_value,
    canonical_shop_id,
    identity_warning_code,
    order_id,
    COALESCE(paid_amount, 0) AS paid_amount,
    COALESCE(product_quantity, 0) AS product_quantity,
    COALESCE(profit, 0) AS profit,
    data_hash,
    ingest_timestamp,
    identity_candidate_count,
    identity_candidates
FROM deduplicated_monthly_orders
WHERE rn = 1;

CREATE INDEX IF NOT EXISTS ix_fact_orders_monthly_atomic_mv_period_platform_shop
ON semantic.fact_orders_monthly_atomic_mv (metric_date, platform_code, shop_id);

CREATE INDEX IF NOT EXISTS ix_fact_orders_monthly_atomic_mv_platform_shop_hash
ON semantic.fact_orders_monthly_atomic_mv (platform_code, shop_id, data_hash);
