CREATE SCHEMA IF NOT EXISTS semantic;

DROP VIEW IF EXISTS semantic.fact_analytics_atomic CASCADE;

CREATE OR REPLACE VIEW semantic.fact_analytics_atomic AS
WITH raw_analytics AS (
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_shopee_analytics_daily
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_shopee_analytics_weekly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_shopee_analytics_monthly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_tiktok_analytics_daily
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_tiktok_analytics_weekly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_tiktok_analytics_monthly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_miaoshou_analytics_daily
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_miaoshou_analytics_weekly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_miaoshou_analytics_monthly
),
mapped AS (
    SELECT
        platform_code,
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
                    raw_data->>'shop_id',
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
        data_domain,
        granularity,
        metric_date::date AS metric_date,
        period_start_date::date AS period_start_date,
        period_end_date::date AS period_end_date,
        period_start_time,
        period_end_time,
        -- ── 取数一律走别名表(单一事实源) ──────────────────────────
        --
        -- 以前这里是 12 段手写 `COALESCE(raw_data->>'...')` 链, 与真实表头
        -- **对不上**的地方全靠「找不到就填 0」掩盖:
        --   * 「曝光次数」「点击次数」—— tiktok 真实列名是「商品曝光次数」
        --     「商品点击量」⇒ 这两个指标**恒 0**;
        --   * 「点击率」—— 两个平台**都没有**这一列 ⇒ 恒 0;
        --   * 「跳出率」—— 全局别名是「跳失率」⇒ shopee 的跳出率取不到。
        --
        -- ⇒ 现在交给 `semantic.resolve_alias()`: 它按「平台精确 → 粒度精确 →
        --   置信度 → 来源 → id」从别名表里挑, 别名表是**唯一事实源**。
        --   取不到就是 NULL(「不知道」), 由输出层如实透出。
        --
        -- ⚠ 这里用 `resolve_alias`(逐字)而不是 `resolve_alias_normalized`:
        --   归一化会把「X」与「X(RMB)」压成同一个 key ⇒ 在两个**不同的
        --   业务事实**之间随机取一个。
        semantic.resolve_alias(raw_data, data_domain, 'visitor_count', platform_code, granularity) AS visitor_count_raw,
        semantic.resolve_alias(raw_data, data_domain, 'page_views', platform_code, granularity) AS page_views_raw,
        semantic.resolve_alias(raw_data, data_domain, 'impressions', platform_code, granularity) AS impressions_raw,
        semantic.resolve_alias(raw_data, data_domain, 'clicks', platform_code, granularity) AS clicks_raw,
        semantic.resolve_alias(raw_data, data_domain, 'click_rate', platform_code, granularity) AS click_rate_raw,
        semantic.resolve_alias(raw_data, data_domain, 'conversion_rate', platform_code, granularity) AS conversion_rate_raw,
        semantic.resolve_alias(raw_data, data_domain, 'order_count', platform_code, granularity) AS order_count_raw,
        semantic.resolve_alias(raw_data, data_domain, 'sku_order_count', platform_code, granularity) AS sku_order_count_raw,
        semantic.resolve_alias(raw_data, data_domain, 'gmv', platform_code, granularity) AS gmv_raw,
        semantic.resolve_alias(raw_data, data_domain, 'total_transaction_amount', platform_code, granularity) AS total_transaction_amount_raw,
        semantic.resolve_alias(raw_data, data_domain, 'product_visitor_count', platform_code, granularity) AS product_visitor_count_raw,
        semantic.resolve_alias(raw_data, data_domain, 'bounce_rate', platform_code, granularity) AS bounce_rate_raw,
        -- [*] 2026-11-09 补登: shopee 独有的 5 个流量指标。
        --   这 5 个别名是**平台限定**的(platform_code='shopee') ⇒ tiktok 数据上
        --   不会命中 ⇒ 不会把 tiktok 的同名/近名列认成这些指标。
        semantic.resolve_alias(raw_data, data_domain, 'new_visitor_count', platform_code, granularity) AS new_visitor_count_raw,
        semantic.resolve_alias(raw_data, data_domain, 'returning_visitor_count', platform_code, granularity) AS returning_visitor_count_raw,
        semantic.resolve_alias(raw_data, data_domain, 'new_follower_count', platform_code, granularity) AS new_follower_count_raw,
        semantic.resolve_alias(raw_data, data_domain, 'avg_session_duration_seconds', platform_code, granularity) AS avg_session_duration_seconds_raw,
        semantic.resolve_alias(raw_data, data_domain, 'avg_page_views_per_visitor', platform_code, granularity) AS avg_page_views_per_visitor_raw,
        raw_data,
        header_columns,
        data_hash,
        ingest_timestamp,
        currency_code
    FROM raw_analytics
),
resolved AS (
    SELECT
        m.platform_code,
        CASE
            WHEN resolved_candidate.candidate_count = 1 THEN resolved_candidate.resolved_shop_id
            ELSE 'unknown'
        END AS shop_id,
        COALESCE(m.source_shop_id, m.store_label_raw) AS raw_shop_id,
        m.store_label_raw,
        resolved_candidate.resolved_shop_account_id,
        CASE
            WHEN resolved_candidate.resolved_shop_id IS NOT NULL THEN resolved_candidate.resolution_method
            WHEN COALESCE(m.source_platform_shop_id, m.source_shop_account_id, m.store_label_raw, m.source_shop_id) IS NULL THEN 'missing_identity'
            ELSE 'unclaimed_identity'
        END AS resolution_method,
        COALESCE(m.source_platform_shop_id, m.source_shop_account_id, m.store_label_raw, m.source_shop_id) AS identity_source_value,
        CASE
            WHEN COALESCE(m.source_platform_shop_id, m.source_shop_account_id, m.store_label_raw, m.source_shop_id) IS NULL
            THEN 'missing_identity'
            WHEN resolved_candidate.candidate_count = 0
            THEN 'unmatched_shop_label'
            WHEN resolved_candidate.candidate_count > 1
            THEN 'ambiguous_shop_label'
            WHEN resolved_candidate.resolved_shop_account_id IS NULL
            THEN 'unresolved_shop_account'
            WHEN resolved_candidate.resolved_shop_account_id IS NOT NULL AND canonical.shop_account_id IS NULL
            THEN 'unresolved_shop_account'
            WHEN resolved_candidate.resolved_shop_account_id IS NOT NULL
             AND LOWER(COALESCE(m.platform_code, '')) IN ('shopee')
             AND NULLIF(TRIM(canonical.platform_shop_id), '') IS NULL
            THEN 'missing_required_platform_shop_id'
            ELSE NULL
        END AS identity_warning_code,
        resolved_candidate.candidate_count AS identity_candidate_count,
        resolved_candidate.candidate_shop_ids::text AS identity_candidates,
        m.data_domain,
        m.granularity,
        m.metric_date,
        m.period_start_date,
        m.period_end_date,
        m.period_start_time,
        m.period_end_time,
        m.visitor_count_raw,
        m.page_views_raw,
        m.impressions_raw,
        m.clicks_raw,
        m.click_rate_raw,
        m.conversion_rate_raw,
        m.order_count_raw,
        m.sku_order_count_raw,
        m.gmv_raw,
        m.total_transaction_amount_raw,
        m.product_visitor_count_raw,
        m.bounce_rate_raw,
        m.new_visitor_count_raw,
        m.returning_visitor_count_raw,
        m.new_follower_count_raw,
        m.avg_session_duration_seconds_raw,
        m.avg_page_views_per_visitor_raw,
        m.raw_data,
        m.header_columns,
        m.data_hash,
        m.ingest_timestamp,
        m.currency_code
    FROM mapped m
    LEFT JOIN LATERAL (
        WITH candidate_values AS (
            -- 候选值集合：必须留在 LATERAL 内部（行相关：引用外层 m.*）
            SELECT candidate.identity_value_normalized
            FROM (
                VALUES
                    (LOWER(COALESCE(m.source_platform_shop_id, ''))),
                    (LOWER(COALESCE(m.source_shop_account_id, ''))),
                    (LOWER(COALESCE(m.source_shop_id, ''))),
                    (
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                LOWER(TRIM(COALESCE(m.source_shop_id, ''))),
                                '^(shopee|tiktok\s*shop|tiktok|tk|miaoshou|amazon|lazada)\s*',
                                '',
                                'i'
                            ),
                            '[[:space:]_()/-]+',
                            '',
                            'g'
                        )
                    ),
                    (
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                LOWER(TRIM(COALESCE(m.store_label_raw, ''))),
                                '^(shopee|tiktok\s*shop|tiktok|tk|miaoshou|amazon|lazada)\s*',
                                '',
                                'i'
                            ),
                            '[[:space:]_()/-]+',
                            '',
                            'g'
                        )
                    )
            ) candidate(identity_value_normalized)
            WHERE NULLIF(candidate.identity_value_normalized, '') IS NOT NULL
        )
        SELECT
            agg.candidate_count,
            agg.candidate_shop_ids,
            best.resolved_shop_id,
            best.resolved_shop_account_id,
            best.resolution_method,
            best.resolution_priority
        FROM (
            -- ① 计数与候选清单：纯聚合，按去重后的店铺算
            SELECT
                count(DISTINCT c.resolved_shop_id)::int AS candidate_count,
                array_agg(DISTINCT c.resolved_shop_id ORDER BY c.resolved_shop_id) AS candidate_shop_ids
            FROM semantic.shop_identity_resolution_candidates_v2_mv c
            WHERE c.platform_code = LOWER(COALESCE(m.platform_code, ''))
              AND c.identity_value_normalized = ANY (ARRAY(SELECT identity_value_normalized FROM candidate_values))
        ) agg
        LEFT JOIN LATERAL (
            -- ② 最优候选：每个店只保留优先级最高的一行
            SELECT DISTINCT ON (c.resolved_shop_id)
                   c.resolved_shop_id,
                   c.resolved_shop_account_id,
                   c.resolution_method,
                   c.resolution_priority
            FROM semantic.shop_identity_resolution_candidates_v2_mv c
            WHERE c.platform_code = LOWER(COALESCE(m.platform_code, ''))
              AND c.identity_value_normalized = ANY (ARRAY(SELECT identity_value_normalized FROM candidate_values))
            ORDER BY c.resolved_shop_id, c.resolution_priority, c.resolution_method
        ) best ON TRUE
        ORDER BY best.resolution_priority, best.resolved_shop_id
        LIMIT 1
    ) resolved_candidate ON TRUE
    LEFT JOIN core.shop_accounts canonical
      ON LOWER(COALESCE(canonical.platform, '')) = LOWER(COALESCE(m.platform_code, ''))
     AND canonical.shop_account_id = resolved_candidate.resolved_shop_account_id
),
cleaned AS (
    SELECT
        platform_code,
        shop_id,
        raw_shop_id,
        store_label_raw,
        resolved_shop_account_id,
        resolution_method,
        identity_source_value,
        identity_warning_code,
        identity_candidate_count,
        identity_candidates,
        data_domain,
        granularity,
        metric_date,
        period_start_date,
        period_end_date,
        period_start_time,
        period_end_time,
        CASE
            WHEN visitor_count_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(visitor_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$' THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(visitor_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS visitor_count,
        CASE
            WHEN page_views_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(page_views_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$' THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(page_views_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS page_views,
        CASE
            WHEN impressions_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(impressions_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$' THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(impressions_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS impressions,
        CASE
            WHEN clicks_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(clicks_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$' THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(clicks_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS clicks,
        CASE
            WHEN click_rate_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(click_rate_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$' THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(click_rate_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric / 100.0
            ELSE NULL
        END AS click_rate,
        CASE
            WHEN conversion_rate_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(conversion_rate_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$' THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(conversion_rate_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric / 100.0
            ELSE NULL
        END AS conversion_rate,
        CASE
            WHEN order_count_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(order_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$' THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(order_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS order_count,
        CASE
            WHEN sku_order_count_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(sku_order_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$' THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(sku_order_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS sku_order_count,
        CASE
            WHEN gmv_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(gmv_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$' THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(gmv_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS gmv,
        CASE
            WHEN total_transaction_amount_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(total_transaction_amount_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$' THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(total_transaction_amount_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS total_transaction_amount,
        CASE
            WHEN product_visitor_count_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(product_visitor_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$' THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(product_visitor_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS product_visitor_count,
        CASE
            WHEN bounce_rate_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(bounce_rate_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$' THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(bounce_rate_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric / 100.0
            ELSE NULL
        END AS bounce_rate,
        -- ── [*] 2026-11-09 补登: shopee 独有的 5 个流量指标 ──────────
        --
        -- ⚠ 清洗链与既有列**完全一致**(去千分位逗号 / 空格 / 破折号 → 正则校验
        --   → numeric) ⇒ 解析不出就是 NULL(「不知道」), 不伪装成 0。
        --   实测这 5 列带千分位逗号(形如 `1,004`)⇒ 必须去逗号。
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
        -- ⚠ 「平均停留时长」是 **HH:MM:SS 字符串**(实测形如 `00:00:42`)——
        --   套普通数值清洗会把 `01:30:00` 变成 `13000`(小时当成了数字)。
        --   ⇒ 这里**专门**换算成秒; 格式不认得 ⇒ NULL(不猜)。
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
        raw_data,
        header_columns,
        data_hash,
        ingest_timestamp,
        currency_code
    FROM resolved
),
deduplicated AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY platform_code, shop_id, data_hash
            ORDER BY
                CASE granularity
                    WHEN 'daily' THEN 1
                    WHEN 'weekly' THEN 2
                    WHEN 'monthly' THEN 3
                    ELSE 9
                END,
                ingest_timestamp DESC
        ) AS rn
    FROM cleaned
)
SELECT
    platform_code,
    shop_id,
    raw_shop_id,
    store_label_raw,
    resolved_shop_account_id,
    resolution_method,
    identity_source_value,
    data_domain,
    granularity,
    metric_date,
    period_start_date,
    period_end_date,
    period_start_time,
    period_end_time,
    -- ⚠ 以前这里一律 `COALESCE(x, 0)`: 源表缺列 / 解析不出 ⇒ 输出 0,
    -- 0 与「真的是 0」在下游**分不开** ⇒ 缺项被当成"没有流量"。
    -- 实测(2026-11 开发库, 改造前): shopee 2355 行、tiktok 1446 行的
    -- impressions / clicks / gmv / order_count **全是 0**, 其中绝大多数是
    -- **取不到值**而不是真的没有。
    --
    -- ⇒ 现在缺项就是 NULL(「不知道」)。下游要按「空 = 没数据」处理,
    --   不要把它当 0 参与求和。
    visitor_count AS visitor_count,
    page_views AS page_views,
    impressions AS impressions,
    clicks AS clicks,
    click_rate AS click_rate,
    conversion_rate AS conversion_rate,
    order_count AS order_count,
    sku_order_count AS sku_order_count,
    gmv AS gmv,
    total_transaction_amount AS total_transaction_amount,
    product_visitor_count AS product_visitor_count,
    bounce_rate AS bounce_rate,
    raw_data,
    header_columns,
    data_hash,
    ingest_timestamp,
    currency_code,
    identity_warning_code,
    identity_candidate_count,
    identity_candidates,
    -- [*] 2026-11-09 补登: shopee 独有的 5 个流量指标。
    --   ⚠ 只能**追加在末尾** —— ``CREATE OR REPLACE VIEW`` 不能删列、
    --   不能改列序(既有列名列序一个都不能动)。
    --   ⚠ 缺项就是 NULL(「不知道」), 与既有列同一口径 ——
    --   不套 ``COALESCE(x, 0)``(tiktok 没有这几列, 填 0 等于说
    --   「tiktok 的新访客是 0 人」= **假的**)。
    new_visitor_count AS new_visitor_count,
    returning_visitor_count AS returning_visitor_count,
    new_follower_count AS new_follower_count,
    avg_session_duration_seconds AS avg_session_duration_seconds,
    avg_page_views_per_visitor AS avg_page_views_per_visitor
FROM deduplicated
WHERE rn = 1;
