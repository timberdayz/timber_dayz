CREATE SCHEMA IF NOT EXISTS semantic;

CREATE OR REPLACE VIEW semantic.fact_analytics_monthly_atomic AS
WITH raw_monthly_traffic AS (
    SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
    FROM b_class.fact_shopee_analytics_monthly
    UNION ALL
    SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
    FROM b_class.fact_tiktok_analytics_monthly
    UNION ALL
    SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
    FROM b_class.fact_miaoshou_analytics_monthly
),
mapped_monthly_traffic AS (
    SELECT
        date_trunc('month', metric_date)::date AS metric_date,
        platform_code,
        COALESCE(
            NULLIF(TRIM(COALESCE(shop_id, '')), ''),
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
            ),
            'unknown'
        ) AS shop_id,
        CASE
            WHEN COALESCE(
                raw_data->>'访客数',
                raw_data->>'独立访客',
                raw_data->>'去重页面浏览次数',
                raw_data->>'unique_visitors',
                raw_data->>'Unique Visitors',
                raw_data->>'uv',
                raw_data->>'visitor_count'
            ) IS NULL THEN NULL
            ELSE NULLIF(
                REGEXP_REPLACE(
                    REPLACE(REPLACE(REPLACE(REPLACE(
                        COALESCE(
                            raw_data->>'访客数',
                            raw_data->>'独立访客',
                            raw_data->>'去重页面浏览次数',
                            raw_data->>'unique_visitors',
                            raw_data->>'Unique Visitors',
                            raw_data->>'uv',
                            raw_data->>'visitor_count'
                        ),
                        ',', ''
                    ), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                    '[^0-9.-]',
                    '',
                    'g'
                ),
                ''
            )::numeric
        END AS visitor_count,
        CASE
            WHEN COALESCE(
                raw_data->>'浏览量',
                raw_data->>'页面浏览次数',
                raw_data->>'page_views',
                raw_data->>'Page Views',
                raw_data->>'views',
                raw_data->>'page_view'
            ) IS NULL THEN NULL
            ELSE NULLIF(
                REGEXP_REPLACE(
                    REPLACE(REPLACE(REPLACE(REPLACE(
                        COALESCE(
                            raw_data->>'浏览量',
                            raw_data->>'页面浏览次数',
                            raw_data->>'page_views',
                            raw_data->>'Page Views',
                            raw_data->>'views',
                            raw_data->>'page_view'
                        ),
                        ',', ''
                    ), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                    '[^0-9.-]',
                    '',
                    'g'
                ),
                ''
            )::numeric
        END AS page_views,
        data_hash,
        ingest_timestamp
    FROM raw_monthly_traffic
),
deduplicated_monthly_traffic AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY platform_code, COALESCE(shop_id, ''), data_hash
            ORDER BY ingest_timestamp DESC
        ) AS rn
    FROM mapped_monthly_traffic
)
SELECT
    metric_date,
    platform_code,
    shop_id,
    visitor_count,
    page_views,
    data_hash,
    ingest_timestamp
FROM deduplicated_monthly_traffic
WHERE rn = 1;
