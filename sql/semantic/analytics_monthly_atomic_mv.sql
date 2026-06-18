CREATE SCHEMA IF NOT EXISTS semantic;

DROP MATERIALIZED VIEW IF EXISTS semantic.fact_analytics_monthly_atomic_mv CASCADE;

CREATE MATERIALIZED VIEW semantic.fact_analytics_monthly_atomic_mv AS
WITH raw_monthly_traffic AS MATERIALIZED (
    SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
    FROM b_class.fact_shopee_analytics_monthly
    UNION ALL
    SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
    FROM b_class.fact_tiktok_analytics_monthly
    UNION ALL
    SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
    FROM b_class.fact_miaoshou_analytics_monthly
),
mapped_monthly_traffic AS MATERIALIZED (
    SELECT
        metric_date::date AS metric_date,
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
        COALESCE(
            CASE
                WHEN LOWER(COALESCE(platform_code, '')) = 'tiktok' THEN raw_data->>'商品访客数'
                ELSE NULL
            END,
            raw_data->>'访客数',
            raw_data->>'独立访客',
            raw_data->>'店铺页面访问量',
            raw_data->>'unique_visitors',
            raw_data->>'Unique Visitors',
            raw_data->>'uv',
            raw_data->>'visitor_count'
        ) AS visitor_count_raw,
        COALESCE(
            raw_data->>'商品访客数',
            raw_data->>'product_visitor_count',
            raw_data->>'Product Visitor Count'
        ) AS product_visitor_count_raw,
        COALESCE(
            raw_data->>'浏览量',
            raw_data->>'页面浏览数',
            raw_data->>'页面浏览次数',
            raw_data->>'page_views',
            raw_data->>'Page Views',
            raw_data->>'views',
            raw_data->>'page_view'
        ) AS page_views_raw,
        COALESCE(raw_data->>'曝光次数', raw_data->>'鏇濆厜娆℃暟', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
        COALESCE(
            raw_data->>'订单数',
            raw_data->>'订单数量',
            raw_data->>'order_count',
            raw_data->>'Order Count'
        ) AS order_count_raw,
        COALESCE(
            raw_data->>'SKU 订单数',
            raw_data->>'sku_order_count',
            raw_data->>'SKU Order Count'
        ) AS sku_order_count_raw,
        COALESCE(
            raw_data->>'GMV',
            raw_data->>'gmv'
        ) AS gmv_raw,
        COALESCE(
            raw_data->>'总成交额',
            raw_data->>'成交金额',
            raw_data->>'sales_amount'
        ) AS total_transaction_amount_raw,
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
            WHEN resolved.resolved_shop_id IS NOT NULL
            THEN COALESCE(NULLIF(TRIM(canonical.platform_shop_id), ''), resolved.resolved_shop_id)
            WHEN COALESCE(m.source_platform_shop_id, m.source_shop_account_id, m.store_label_raw, m.source_shop_id) IS NULL THEN 'unknown'
            ELSE COALESCE(m.source_platform_shop_id, m.source_shop_account_id, m.store_label_raw, m.source_shop_id)
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
            WHEN resolved.resolved_shop_account_id IS NOT NULL AND canonical.shop_account_id IS NULL
            THEN 'missing_shop_account_authority'
            WHEN resolved.resolved_shop_account_id IS NOT NULL AND NULLIF(TRIM(canonical.platform_shop_id), '') IS NULL
            THEN 'missing_canonical_shop_id'
            ELSE NULL
        END AS identity_warning_code,
        m.visitor_count,
        m.product_visitor_count,
        m.page_views,
        m.impressions,
        m.order_count,
        m.sku_order_count,
        m.gmv,
        m.total_transaction_amount,
        m.data_hash,
        m.ingest_timestamp
    FROM normalized_monthly_traffic m
    LEFT JOIN LATERAL (
        SELECT
            c.resolved_shop_id,
            c.resolved_shop_account_id,
            c.resolution_method,
            c.resolution_priority,
            c.identity_source_value
        FROM semantic.shop_identity_resolution_candidates c
        WHERE c.platform_code = LOWER(COALESCE(m.platform_code, ''))
          AND c.identity_value_normalized = ANY (m.normalized_identity_candidates)
        ORDER BY c.resolution_priority, c.resolved_shop_id
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
    ingest_timestamp
FROM deduplicated_monthly_traffic
WHERE rn = 1;

CREATE INDEX IF NOT EXISTS ix_fact_analytics_monthly_atomic_mv_period_platform_shop
ON semantic.fact_analytics_monthly_atomic_mv (metric_date, platform_code, shop_id);

CREATE INDEX IF NOT EXISTS ix_fact_analytics_monthly_atomic_mv_platform_shop_hash
ON semantic.fact_analytics_monthly_atomic_mv (platform_code, shop_id, data_hash);
