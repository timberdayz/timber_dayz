CREATE SCHEMA IF NOT EXISTS semantic;

CREATE OR REPLACE VIEW semantic.fact_services_atomic AS
WITH raw_services AS (
    SELECT platform_code, shop_id, data_domain, granularity, sub_domain, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_shopee_services_agent_daily
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, sub_domain, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_shopee_services_agent_weekly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, sub_domain, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_shopee_services_agent_monthly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, sub_domain, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_shopee_services_ai_assistant_daily
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, sub_domain, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_shopee_services_ai_assistant_weekly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, sub_domain, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_shopee_services_ai_assistant_monthly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, sub_domain, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_tiktok_services_agent_daily
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, sub_domain, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_tiktok_services_agent_weekly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, sub_domain, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_tiktok_services_agent_monthly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, sub_domain, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_tiktok_services_ai_assistant_daily
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, sub_domain, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_tiktok_services_ai_assistant_weekly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, sub_domain, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_tiktok_services_ai_assistant_monthly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, sub_domain, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_miaoshou_services_agent_daily
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, sub_domain, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_miaoshou_services_agent_weekly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, sub_domain, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_miaoshou_services_agent_monthly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, sub_domain, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_miaoshou_services_ai_assistant_daily
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, sub_domain, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_miaoshou_services_ai_assistant_weekly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, sub_domain, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_miaoshou_services_ai_assistant_monthly
),
mapped AS (
    SELECT
        platform_code,
        COALESCE(NULLIF(TRIM(COALESCE(shop_id, '')), ''), 'unknown') AS shop_id,
        data_domain,
        granularity,
        sub_domain,
        metric_date::date AS metric_date,
        period_start_date::date AS period_start_date,
        period_end_date::date AS period_end_date,
        period_start_time,
        period_end_time,
        COALESCE(raw_data->>'访客数', raw_data->>'visitors', raw_data->>'Visitors', raw_data->>'访客') AS visitor_count_raw,
        COALESCE(raw_data->>'聊天询问', raw_data->>'chats', raw_data->>'Chats', raw_data->>'询问', raw_data->>'聊天数') AS chat_count_raw,
        COALESCE(raw_data->>'订单', raw_data->>'orders', raw_data->>'Orders', raw_data->>'订单数', raw_data->>'买家数') AS order_count_raw,
        COALESCE(raw_data->>'销售额', raw_data->>'gmv', raw_data->>'GMV', raw_data->>'sales', raw_data->>'成交金额') AS gmv_raw,
        COALESCE(raw_data->>'满意度', raw_data->>'satisfaction', raw_data->>'Satisfaction', raw_data->>'用户满意度') AS satisfaction_raw,
        raw_data,
        header_columns,
        data_hash,
        ingest_timestamp,
        currency_code
    FROM raw_services
),
cleaned AS (
    SELECT
        platform_code,
        shop_id,
        data_domain,
        granularity,
        sub_domain,
        metric_date,
        period_start_date,
        period_end_date,
        period_start_time,
        period_end_time,
        CASE WHEN visitor_count_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(visitor_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric END AS visitor_count,
        CASE WHEN chat_count_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(chat_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric END AS chat_count,
        CASE WHEN order_count_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(order_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric END AS order_count,
        CASE WHEN gmv_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(gmv_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric END AS gmv,
        CASE WHEN satisfaction_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(satisfaction_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric / 100.0 END AS satisfaction,
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
    sub_domain,
    metric_date,
    period_start_date,
    period_end_date,
    period_start_time,
    period_end_time,
    COALESCE(period_end_date, metric_date) AS service_date,
    COALESCE(period_start_date, metric_date) AS service_start_date,
    COALESCE(period_end_date, metric_date) AS service_end_date,
    COALESCE(visitor_count, 0) AS visitor_count,
    COALESCE(chat_count, 0) AS chat_count,
    COALESCE(order_count, 0) AS order_count,
    COALESCE(gmv, 0) AS gmv,
    COALESCE(satisfaction, 0) AS satisfaction,
    raw_data,
    header_columns,
    data_hash,
    ingest_timestamp,
    currency_code
FROM deduplicated
WHERE rn = 1;
