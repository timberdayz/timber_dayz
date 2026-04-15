CREATE SCHEMA IF NOT EXISTS semantic;

DROP VIEW IF EXISTS semantic.fact_analytics_monthly_atomic CASCADE;

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
                raw_data->>'页面浏览数',
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
                            raw_data->>'页面浏览数',
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
resolved_monthly_traffic AS (
    SELECT
        m.metric_date,
        m.platform_code,
        CASE
            WHEN resolved.resolved_shop_id IS NOT NULL THEN resolved.resolved_shop_id
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
        COALESCE(m.source_platform_shop_id, m.source_shop_account_id, m.store_label_raw, m.source_shop_id) AS identity_source_value,
        m.visitor_count,
        m.page_views,
        m.data_hash,
        m.ingest_timestamp
    FROM mapped_monthly_traffic m
    LEFT JOIN LATERAL (
        SELECT
            c.resolved_shop_id,
            c.resolved_shop_account_id,
            c.resolution_method,
            c.resolution_priority
        FROM semantic.shop_identity_resolution_candidates c
        WHERE c.platform_code = LOWER(COALESCE(m.platform_code, ''))
          AND c.identity_value_normalized IN (
              LOWER(COALESCE(m.source_platform_shop_id, '')),
              LOWER(COALESCE(m.source_shop_account_id, '')),
              LOWER(COALESCE(m.source_shop_id, '')),
              REGEXP_REPLACE(
                  REGEXP_REPLACE(LOWER(TRIM(COALESCE(m.source_shop_id, ''))), '^(shopee|tiktok\s*shop|tiktok|tk|miaoshou|amazon|lazada)\s*', '', 'i'),
                  '[[:space:]_()/-]+',
                  '',
                  'g'
              ),
              REGEXP_REPLACE(
                  REGEXP_REPLACE(LOWER(TRIM(COALESCE(m.store_label_raw, ''))), '^(shopee|tiktok\s*shop|tiktok|tk|miaoshou|amazon|lazada)\s*', '', 'i'),
                  '[[:space:]_()/-]+',
                  '',
                  'g'
              )
          )
        ORDER BY c.resolution_priority, c.resolved_shop_id
        LIMIT 1
    ) resolved ON TRUE
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
    visitor_count,
    page_views,
    data_hash,
    ingest_timestamp
FROM deduplicated_monthly_traffic
WHERE rn = 1;
