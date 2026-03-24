CREATE SCHEMA IF NOT EXISTS semantic;

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
        COALESCE(
            NULLIF(TRIM(COALESCE(shop_id, '')), ''),
            NULLIF(TRIM(COALESCE(
                raw_data->>'店铺',
                raw_data->>'店铺名',
                raw_data->>'店铺名称',
                raw_data->>'store_name',
                raw_data->>'store_label_raw'
            )), ''),
            'unknown'
        ) AS shop_id,
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
            raw_data->>'unique_visitors',
            raw_data->>'Unique Visitors',
            raw_data->>'uv',
            raw_data->>'visitor_count'
        ) AS visitor_count_raw,
        COALESCE(
            raw_data->>'浏览量',
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
        COALESCE(raw_data->>'成交金额', raw_data->>'GMV', raw_data->>'gmv', raw_data->>'sales_amount') AS gmv_raw,
        COALESCE(raw_data->>'跳出率', raw_data->>'bounce_rate', raw_data->>'Bounce Rate') AS bounce_rate_raw,
        raw_data,
        header_columns,
        data_hash,
        ingest_timestamp,
        currency_code
    FROM raw_analytics
),
cleaned AS (
    SELECT
        platform_code,
        shop_id,
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
            WHEN gmv_raw IS NULL THEN NULL
            ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(gmv_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
        END AS gmv,
        CASE
            WHEN bounce_rate_raw IS NULL THEN NULL
            ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(bounce_rate_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric / 100.0
        END AS bounce_rate,
        raw_data,
        header_columns,
        data_hash,
        ingest_timestamp,
        currency_code
    FROM mapped
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
    COALESCE(gmv, 0) AS gmv,
    COALESCE(bounce_rate, 0) AS bounce_rate,
    raw_data,
    header_columns,
    data_hash,
    ingest_timestamp,
    currency_code
FROM deduplicated
WHERE rn = 1;
