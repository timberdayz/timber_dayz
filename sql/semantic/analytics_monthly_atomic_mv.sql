CREATE SCHEMA IF NOT EXISTS semantic;

DROP MATERIALIZED VIEW IF EXISTS semantic.fact_analytics_monthly_atomic_mv CASCADE;

CREATE MATERIALIZED VIEW semantic.fact_analytics_monthly_atomic_mv AS
WITH raw_monthly_traffic AS MATERIALIZED (
    SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp, data_domain
    FROM b_class.fact_shopee_analytics_monthly
    UNION ALL
    SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp, data_domain
    FROM b_class.fact_tiktok_analytics_monthly
    UNION ALL
    SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp, data_domain
    FROM b_class.fact_miaoshou_analytics_monthly
),
mapped_monthly_traffic AS MATERIALIZED (
    SELECT
        metric_date::date AS metric_date,
        platform_code,
        data_domain,
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
        -- ── 取数一律走别名表(单一事实源) ──────────────────────────
        --
        -- 以前这里是手写 `COALESCE(raw_data->>'...')` 链, 与真实表头对不上的
        -- 地方全靠「找不到就填 0」掩盖 ⇒ **「不知道」被伪装成「0」**。
        --
        -- ⇒ 现在交给 `semantic.resolve_alias()`(别名表是唯一事实源):
        --   取不到就是 NULL(「不知道」), 由输出层如实透出。
        --
        -- ⚠ 与日/周链(`sql/semantic/analytics_atomic.sql`)口径一致 ——
        --   两条链同源(b_class 的 analytics 月度/日周源表), 不允许一个指标
        --   在两条链上取到不同的列。
        semantic.resolve_alias(raw_data, data_domain, 'visitor_count', platform_code, 'monthly') AS visitor_count_raw,
        semantic.resolve_alias(raw_data, data_domain, 'product_visitor_count', platform_code, 'monthly') AS product_visitor_count_raw,
        semantic.resolve_alias(raw_data, data_domain, 'page_views', platform_code, 'monthly') AS page_views_raw,
        semantic.resolve_alias(raw_data, data_domain, 'impressions', platform_code, 'monthly') AS impressions_raw,
        semantic.resolve_alias(raw_data, data_domain, 'order_count', platform_code, 'monthly') AS order_count_raw,
        semantic.resolve_alias(raw_data, data_domain, 'sku_order_count', platform_code, 'monthly') AS sku_order_count_raw,
        semantic.resolve_alias(raw_data, data_domain, 'gmv', platform_code, 'monthly') AS gmv_raw,
        semantic.resolve_alias(raw_data, data_domain, 'total_transaction_amount', platform_code, 'monthly') AS total_transaction_amount_raw,
        -- [*] 2026-11-09 补登: shopee 独有的 5 个流量指标。
        --   平台限定别名(platform_code='shopee') ⇒ tiktok 数据上不会命中。
        --   ⚠ 与日/周链(`sql/semantic/analytics_atomic.sql`)**同源同口径** ——
        --   同一个指标在两条链上必须取到同一个列、同一套清洗规则。
        semantic.resolve_alias(raw_data, data_domain, 'new_visitor_count', platform_code, 'monthly') AS new_visitor_count_raw,
        semantic.resolve_alias(raw_data, data_domain, 'returning_visitor_count', platform_code, 'monthly') AS returning_visitor_count_raw,
        semantic.resolve_alias(raw_data, data_domain, 'new_follower_count', platform_code, 'monthly') AS new_follower_count_raw,
        semantic.resolve_alias(raw_data, data_domain, 'avg_session_duration_seconds', platform_code, 'monthly') AS avg_session_duration_seconds_raw,
        semantic.resolve_alias(raw_data, data_domain, 'avg_page_views_per_visitor', platform_code, 'monthly') AS avg_page_views_per_visitor_raw,
        data_hash,
        ingest_timestamp
    FROM raw_monthly_traffic
),
normalized_monthly_traffic AS MATERIALIZED (
    SELECT
        metric_date,
        platform_code,
        source_shop_id,
        store_label_raw,
        source_platform_shop_id,
        source_shop_account_id,
        CASE
            WHEN visitor_count_raw IS NULL THEN NULL
            ELSE CASE
                WHEN NULLIF(
                    REGEXP_REPLACE(
                        REPLACE(REPLACE(REPLACE(REPLACE(visitor_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                        '[^0-9.-]',
                        '',
                        'g'
                    ),
                    ''
                ) IN ('-', '.', '-.') THEN NULL
                ELSE NULLIF(
                    REGEXP_REPLACE(
                        REPLACE(REPLACE(REPLACE(REPLACE(visitor_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                        '[^0-9.-]',
                        '',
                        'g'
                    ),
                    ''
                )::numeric
            END
        END AS visitor_count,
        CASE
            WHEN product_visitor_count_raw IS NULL THEN NULL
            ELSE CASE
                WHEN NULLIF(
                    REGEXP_REPLACE(
                        REPLACE(REPLACE(REPLACE(REPLACE(product_visitor_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                        '[^0-9.-]',
                        '',
                        'g'
                    ),
                    ''
                ) IN ('-', '.', '-.') THEN NULL
                ELSE NULLIF(
                    REGEXP_REPLACE(
                        REPLACE(REPLACE(REPLACE(REPLACE(product_visitor_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                        '[^0-9.-]',
                        '',
                        'g'
                    ),
                    ''
                )::numeric
            END
        END AS product_visitor_count,
        CASE
            WHEN page_views_raw IS NULL THEN NULL
            ELSE CASE
                WHEN NULLIF(
                    REGEXP_REPLACE(
                        REPLACE(REPLACE(REPLACE(REPLACE(page_views_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                        '[^0-9.-]',
                        '',
                        'g'
                    ),
                    ''
                ) IN ('-', '.', '-.') THEN NULL
                ELSE NULLIF(
                    REGEXP_REPLACE(
                        REPLACE(REPLACE(REPLACE(REPLACE(page_views_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                        '[^0-9.-]',
                        '',
                        'g'
                    ),
                    ''
                )::numeric
            END
        END AS page_views,
        CASE
            WHEN impressions_raw IS NULL THEN NULL
            ELSE CASE
                WHEN NULLIF(
                    REGEXP_REPLACE(
                        REPLACE(REPLACE(REPLACE(REPLACE(impressions_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                        '[^0-9.-]',
                        '',
                        'g'
                    ),
                    ''
                ) IN ('-', '.', '-.') THEN NULL
                ELSE NULLIF(
                    REGEXP_REPLACE(
                        REPLACE(REPLACE(REPLACE(REPLACE(impressions_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                        '[^0-9.-]',
                        '',
                        'g'
                    ),
                    ''
                )::numeric
            END
        END AS impressions,
        CASE
            WHEN order_count_raw IS NULL THEN NULL
            ELSE CASE
                WHEN NULLIF(
                    REGEXP_REPLACE(
                        REPLACE(REPLACE(REPLACE(REPLACE(order_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                        '[^0-9.-]',
                        '',
                        'g'
                    ),
                    ''
                ) IN ('-', '.', '-.') THEN NULL
                ELSE NULLIF(
                    REGEXP_REPLACE(
                        REPLACE(REPLACE(REPLACE(REPLACE(order_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                        '[^0-9.-]',
                        '',
                        'g'
                    ),
                    ''
                )::numeric
            END
        END AS order_count,
        CASE
            WHEN sku_order_count_raw IS NULL THEN NULL
            ELSE CASE
                WHEN NULLIF(
                    REGEXP_REPLACE(
                        REPLACE(REPLACE(REPLACE(REPLACE(sku_order_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                        '[^0-9.-]',
                        '',
                        'g'
                    ),
                    ''
                ) IN ('-', '.', '-.') THEN NULL
                ELSE NULLIF(
                    REGEXP_REPLACE(
                        REPLACE(REPLACE(REPLACE(REPLACE(sku_order_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                        '[^0-9.-]',
                        '',
                        'g'
                    ),
                    ''
                )::numeric
            END
        END AS sku_order_count,
        CASE
            WHEN gmv_raw IS NULL THEN NULL
            ELSE CASE
                WHEN NULLIF(
                    REGEXP_REPLACE(
                        REPLACE(REPLACE(REPLACE(REPLACE(gmv_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                        '[^0-9.-]',
                        '',
                        'g'
                    ),
                    ''
                ) IN ('-', '.', '-.') THEN NULL
                ELSE NULLIF(
                    REGEXP_REPLACE(
                        REPLACE(REPLACE(REPLACE(REPLACE(gmv_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                        '[^0-9.-]',
                        '',
                        'g'
                    ),
                    ''
                )::numeric
            END
        END AS gmv,
        CASE
            WHEN total_transaction_amount_raw IS NULL THEN NULL
            ELSE CASE
                WHEN NULLIF(
                    REGEXP_REPLACE(
                        REPLACE(REPLACE(REPLACE(REPLACE(total_transaction_amount_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                        '[^0-9.-]',
                        '',
                        'g'
                    ),
                    ''
                ) IN ('-', '.', '-.') THEN NULL
                ELSE NULLIF(
                    REGEXP_REPLACE(
                        REPLACE(REPLACE(REPLACE(REPLACE(total_transaction_amount_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                        '[^0-9.-]',
                        '',
                        'g'
                    ),
                    ''
                )::numeric
            END
        END AS total_transaction_amount,
        -- ── [*] 2026-11-09 补登: shopee 独有的 5 个流量指标 ──────────
        --
        -- ⚠ 清洗链与**日/周链完全一致**(去千分位逗号 / 空格 / 破折号 →
        --   正则校验 → numeric) ⇒ 两条链解析不出时都是 NULL(「不知道」),
        --   绝不伪装成 0。实测这 5 列带千分位逗号(形如 `1,004`)⇒ 必须去逗号。
        CASE
            WHEN new_visitor_count_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(new_visitor_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$' THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(new_visitor_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS new_visitor_count,
        CASE
            WHEN returning_visitor_count_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(returning_visitor_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$' THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(returning_visitor_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS returning_visitor_count,
        CASE
            WHEN new_follower_count_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(new_follower_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$' THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(new_follower_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS new_follower_count,
        -- ⚠ 「平均停留时长」是 **HH:MM:SS 字符串**(形如 `00:00:42`)——
        --   套普通数值清洗会把 `01:30:00` 变成 `13000` ⇒ 这里**专门**换算成秒;
        --   格式不认得 ⇒ NULL(不猜)。
        CASE
            WHEN avg_session_duration_seconds_raw IS NULL THEN NULL
            WHEN TRIM(avg_session_duration_seconds_raw) ~ '^(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$' THEN
                split_part(TRIM(avg_session_duration_seconds_raw), ':', 1)::numeric * 3600
                + split_part(TRIM(avg_session_duration_seconds_raw), ':', 2)::numeric * 60
                + split_part(TRIM(avg_session_duration_seconds_raw), ':', 3)::numeric
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(avg_session_duration_seconds_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$' THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(avg_session_duration_seconds_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS avg_session_duration_seconds,
        CASE
            WHEN avg_page_views_per_visitor_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(avg_page_views_per_visitor_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$' THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(avg_page_views_per_visitor_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS avg_page_views_per_visitor,
        ARRAY_REMOVE(
            ARRAY[
                LOWER(COALESCE(source_platform_shop_id, '')),
                LOWER(COALESCE(source_shop_account_id, '')),
                CASE
                    WHEN LOWER(COALESCE(source_shop_id, '')) NOT IN ('xihong', 'unknown', 'none')
                    THEN LOWER(COALESCE(source_shop_id, ''))
                END,
                CASE
                    WHEN LOWER(COALESCE(source_shop_id, '')) NOT IN ('xihong', 'unknown', 'none')
                    THEN REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            LOWER(TRIM(COALESCE(source_shop_id, ''))),
                            '^(shopee|tiktok\s*shop|tiktok|tk|miaoshou|amazon|lazada)\s*',
                            '',
                            'i'
                        ),
                        '[[:space:]_()/-]+',
                        '',
                        'g'
                    )
                END,
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
                )
            ],
            ''
        ) AS normalized_identity_candidates,
        data_hash,
        ingest_timestamp
    FROM mapped_monthly_traffic
),
resolved_monthly_traffic AS MATERIALIZED (
    SELECT
        m.metric_date,
        m.platform_code,
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
        m.visitor_count,
        m.product_visitor_count,
        m.page_views,
        m.impressions,
        m.order_count,
        m.sku_order_count,
        m.gmv,
        m.total_transaction_amount,
        m.new_visitor_count,
        m.returning_visitor_count,
        m.new_follower_count,
        m.avg_session_duration_seconds,
        m.avg_page_views_per_visitor,
        m.data_hash,
        m.ingest_timestamp
    FROM normalized_monthly_traffic m
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
            ORDER BY c.resolved_shop_id, c.resolution_priority, c.resolution_method, c.identity_source_value
        ) best ON TRUE
        ORDER BY best.resolution_priority, best.resolved_shop_id
        LIMIT 1
    ) resolved ON TRUE
    LEFT JOIN core.shop_accounts canonical
      ON LOWER(COALESCE(canonical.platform, '')) = LOWER(COALESCE(m.platform_code, ''))
     AND canonical.shop_account_id = resolved.resolved_shop_account_id
),
deduplicated_monthly_traffic AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY platform_code, COALESCE(shop_id, ''), data_hash
            ORDER BY ingest_timestamp DESC
        ) AS rn
    FROM resolved_monthly_traffic
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
    visitor_count,
    product_visitor_count,
    page_views,
    impressions,
    order_count,
    sku_order_count,
    gmv,
    total_transaction_amount,
    data_hash,
    ingest_timestamp,
    identity_candidate_count,
    identity_candidates,
    -- [*] 2026-11-09 补登: shopee 独有的 5 个流量指标。
    --   ⚠ 只能**追加在末尾** —— 物化视图的列集变了必须 DROP + 重建。
    --   ⚠ 缺项就是 NULL(「不知道」), 与既有列同一口径。
    new_visitor_count,
    returning_visitor_count,
    new_follower_count,
    avg_session_duration_seconds,
    avg_page_views_per_visitor
FROM deduplicated_monthly_traffic
WHERE rn = 1;

CREATE INDEX IF NOT EXISTS ix_fact_analytics_monthly_atomic_mv_period_platform_shop
ON semantic.fact_analytics_monthly_atomic_mv (metric_date, platform_code, shop_id);

CREATE INDEX IF NOT EXISTS ix_fact_analytics_monthly_atomic_mv_platform_shop_hash
ON semantic.fact_analytics_monthly_atomic_mv (platform_code, shop_id, data_hash);
