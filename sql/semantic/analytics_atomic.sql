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
        COALESCE(
            raw_data->>'访客数',
            raw_data->>'独立访客',
            raw_data->>'去重页面浏览次数',
            raw_data->>'店铺页面访问量',
            raw_data->>'unique_visitors',
            raw_data->>'Unique Visitors',
            raw_data->>'uv',
            raw_data->>'visitor_count'
        ) AS visitor_count_raw,
        COALESCE(
            raw_data->>'浏览量',
            raw_data->>'页面浏览数',
            raw_data->>'页面浏览次数',
            raw_data->>'page_views',
            raw_data->>'Page Views',
            raw_data->>'views',
            raw_data->>'page_view'
        ) AS page_views_raw,
        COALESCE(raw_data->>'曝光次数', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
        COALESCE(raw_data->>'点击次数', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
        COALESCE(raw_data->>'点击率', raw_data->>'click_rate', raw_data->>'Click Rate', raw_data->>'CTR') AS click_rate_raw,
        COALESCE(raw_data->>'转化率', raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
        COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count') AS order_count_raw,
        COALESCE(raw_data->>'SKU 订单数', raw_data->>'sku_order_count', raw_data->>'SKU Order Count') AS sku_order_count_raw,
        COALESCE(raw_data->>'GMV', raw_data->>'gmv') AS gmv_raw,
        COALESCE(raw_data->>'总成交额', raw_data->>'成交金额', raw_data->>'sales_amount') AS total_transaction_amount_raw,
        COALESCE(raw_data->>'商品访客数', raw_data->>'product_visitor_count', raw_data->>'Product Visitor Count') AS product_visitor_count_raw,
        COALESCE(raw_data->>'跳出率', raw_data->>'bounce_rate', raw_data->>'Bounce Rate') AS bounce_rate_raw,
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
            WHEN resolved_candidate.resolved_shop_id IS NOT NULL THEN resolved_candidate.resolved_shop_id
            WHEN COALESCE(m.source_platform_shop_id, m.source_shop_account_id, m.store_label_raw, m.source_shop_id) IS NULL THEN 'unknown'
            ELSE COALESCE(m.source_platform_shop_id, m.source_shop_account_id, m.store_label_raw, m.source_shop_id)
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
        m.raw_data,
        m.header_columns,
        m.data_hash,
        m.ingest_timestamp,
        m.currency_code
    FROM mapped m
    LEFT JOIN LATERAL (
        SELECT
            c.resolved_shop_id,
            c.resolved_shop_account_id,
            c.resolution_method,
            c.resolution_priority
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
        INNER JOIN semantic.shop_identity_resolution_candidates c
          ON c.platform_code = LOWER(COALESCE(m.platform_code, ''))
         AND c.identity_value_normalized = candidate.identity_value_normalized
        WHERE NULLIF(candidate.identity_value_normalized, '') IS NOT NULL
        ORDER BY c.resolution_priority, c.resolved_shop_id
        LIMIT 1
    ) resolved_candidate ON TRUE
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
        data_domain,
        granularity,
        metric_date,
        period_start_date,
        period_end_date,
        period_start_time,
        period_end_time,
        CASE
            WHEN visitor_count_raw IS NULL THEN NULL
            ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(visitor_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
        END AS visitor_count,
        CASE
            WHEN page_views_raw IS NULL THEN NULL
            ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(page_views_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
        END AS page_views,
        CASE
            WHEN impressions_raw IS NULL THEN NULL
            ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(impressions_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
        END AS impressions,
        CASE
            WHEN clicks_raw IS NULL THEN NULL
            ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(clicks_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
        END AS clicks,
        CASE
            WHEN click_rate_raw IS NULL THEN NULL
            ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(click_rate_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric / 100.0
        END AS click_rate,
        CASE
            WHEN conversion_rate_raw IS NULL THEN NULL
            ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(conversion_rate_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric / 100.0
        END AS conversion_rate,
        CASE
            WHEN order_count_raw IS NULL THEN NULL
            ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(order_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
        END AS order_count,
        CASE
            WHEN sku_order_count_raw IS NULL THEN NULL
            ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(sku_order_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
        END AS sku_order_count,
        CASE
            WHEN gmv_raw IS NULL THEN NULL
            ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(gmv_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
        END AS gmv,
        CASE
            WHEN total_transaction_amount_raw IS NULL THEN NULL
            ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(total_transaction_amount_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
        END AS total_transaction_amount,
        CASE
            WHEN product_visitor_count_raw IS NULL THEN NULL
            ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(product_visitor_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
        END AS product_visitor_count,
        CASE
            WHEN bounce_rate_raw IS NULL THEN NULL
            ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(bounce_rate_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric / 100.0
        END AS bounce_rate,
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
    COALESCE(visitor_count, 0) AS visitor_count,
    COALESCE(page_views, 0) AS page_views,
    COALESCE(impressions, 0) AS impressions,
    COALESCE(clicks, 0) AS clicks,
    COALESCE(click_rate, 0) AS click_rate,
    COALESCE(conversion_rate, 0) AS conversion_rate,
    COALESCE(order_count, 0) AS order_count,
    COALESCE(sku_order_count, 0) AS sku_order_count,
    COALESCE(gmv, 0) AS gmv,
    COALESCE(total_transaction_amount, 0) AS total_transaction_amount,
    COALESCE(product_visitor_count, 0) AS product_visitor_count,
    COALESCE(bounce_rate, 0) AS bounce_rate,
    raw_data,
    header_columns,
    data_hash,
    ingest_timestamp,
    currency_code
FROM deduplicated
WHERE rn = 1;
