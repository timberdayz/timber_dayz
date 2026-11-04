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
        -- 原始店铺标识（采集层写进来的）。解析前保留，最后再换成规范键。
        COALESCE(NULLIF(TRIM(COALESCE(shop_id, '')), ''), 'unknown') AS source_shop_id,
        -- 身份候选值：与 orders_atomic 的 normalized_identity_candidates 同构。
        -- raw_data 里的 shop_account_id 是采集文件自带的店铺账号ID —— 最可靠的一路。
        ARRAY_REMOVE(
            ARRAY[
                LOWER(COALESCE(NULLIF(TRIM(COALESCE(raw_data->>'shop_account_id', '')), ''), '')),
                LOWER(COALESCE(NULLIF(TRIM(COALESCE(raw_data->>'platform_shop_id', '')), ''), '')),
                LOWER(COALESCE(NULLIF(TRIM(COALESCE(raw_data->>'shop_id', '')), ''), '')),
                LOWER(COALESCE(NULLIF(TRIM(COALESCE(shop_id, '')), ''), '')),
                REGEXP_REPLACE(
                    REGEXP_REPLACE(
                        LOWER(TRIM(COALESCE(NULLIF(TRIM(COALESCE(raw_data->>'store_name', '')), ''), ''))),
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
        ) AS identity_candidates,
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
        COALESCE(raw_data->>'订单', raw_data->>'orders', raw_data->>'Orders', raw_data->>'订单数') AS order_count_raw,
        COALESCE(raw_data->>'买家数', raw_data->>'buyer_count', raw_data->>'Buyer Count') AS buyer_count_raw,
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
        source_shop_id,
        identity_candidates,
        data_domain,
        granularity,
        sub_domain,
        metric_date,
        period_start_date,
        period_end_date,
        period_start_time,
        period_end_time,
        CASE
            WHEN visitor_count_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(visitor_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(visitor_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS visitor_count,
        CASE
            WHEN chat_count_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(chat_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(chat_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS chat_count,
        CASE
            WHEN order_count_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(order_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(order_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS order_count,
        CASE
            WHEN buyer_count_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(buyer_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(buyer_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS buyer_count,
        CASE
            WHEN gmv_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(gmv_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(gmv_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS gmv,
        CASE
            WHEN satisfaction_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(satisfaction_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(satisfaction_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric / 100.0
            ELSE NULL
        END AS satisfaction,
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
            PARTITION BY platform_code, source_shop_id, data_hash
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
),
resolved AS (
    -- 解析成规范店铺键（口径见 sql/semantic/shop_identity_resolver.sql）。
    -- 候选 = 1 ⇒ 用规范键（唯一命中）。
    -- 候选 = 0 ⇒ 这个店在本系统里没有账号 ⇒ **保留原始键**。
    -- 候选 > 1 ⇒ 有歧义 ⇒ **也保留原始键**：
    --   原始键是采集文件里数据自己写的（如平台店铺ID，有唯一约束），
    --   歧义来自「同一个源行的其它身份路径命中了别的账号」。
    --   抹成 unknown 会让看板再也查不到店名（显示名 JOIN 靠的正是原始键），
    --   猜一个则是在编数据 ⇒ 两者都不做，保留原值 + 暴露候选数。
    SELECT
        d.*,
        CASE
            WHEN r.candidate_count = 1 THEN r.resolved_shop_id
            ELSE d.source_shop_id
        END AS shop_id,
        r.resolved_shop_account_id AS resolved_shop_account_id,
        COALESCE(r.candidate_count, 0) AS identity_candidate_count
    FROM deduplicated d
    LEFT JOIN LATERAL (
        SELECT *
          FROM semantic.resolve_shop_identity(d.platform_code, d.identity_candidates, NULL)
    ) r ON TRUE
    WHERE d.rn = 1
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
    currency_code,
    COALESCE(buyer_count, 0) AS buyer_count,
    -- ↓ 新增列必须追加在末尾（CREATE OR REPLACE VIEW 不允许改变已有列的位置）
    -- 解析出的店铺账号ID（NULL = 没解析出来，键仍是原始标识）。
    resolved_shop_account_id,
    -- 身份候选数：0 = 没匹配到账号；1 = 唯一命中；>1 = 有歧义（已落 unknown）。
    identity_candidate_count
FROM resolved;
