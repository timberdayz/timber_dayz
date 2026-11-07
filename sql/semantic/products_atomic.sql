CREATE SCHEMA IF NOT EXISTS semantic;

CREATE OR REPLACE VIEW semantic.fact_products_atomic AS
WITH raw_products AS (
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_shopee_products_daily
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_shopee_products_weekly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_shopee_products_monthly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_tiktok_products_daily
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_tiktok_products_weekly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_tiktok_products_monthly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_miaoshou_products_daily
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_miaoshou_products_weekly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_miaoshou_products_monthly
),
mapped AS (
    SELECT
        platform_code,
        -- 原始店铺标识（采集层写进来的）。解析前保留，最后再换成规范键。
        -- 注意 tiktok 的商品采集文件只带「地区(店名)」这种店名（例：Malaysia(Flora Mall)），
        -- 当前候选集里没有对应账号 ⇒ 这类行会保留原始键（候选=0），不会被抹成 unknown。
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
        metric_date::date AS metric_date,
        period_start_date::date AS period_start_date,
        period_end_date::date AS period_end_date,
        period_start_time,
        period_end_time,
        semantic.resolve_alias(raw_data, data_domain, 'product_id', platform_code, granularity) AS product_id,
        semantic.resolve_alias(raw_data, data_domain, 'product_name', platform_code, granularity) AS product_name,
        COALESCE(raw_data->>'平台SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku,
        COALESCE(raw_data->>'类目', raw_data->>'分类', raw_data->>'category', raw_data->>'Category') AS category,
        semantic.resolve_alias(raw_data, data_domain, 'item_status', platform_code, granularity) AS item_status,
        COALESCE(raw_data->>'价格', raw_data->>'单价', raw_data->>'售价', raw_data->>'price', raw_data->>'Price') AS price_raw,
        COALESCE(raw_data->>'库存', raw_data->>'库存数量', raw_data->>'stock', raw_data->>'Stock', raw_data->>'inventory') AS stock_raw,
        COALESCE(raw_data->>'浏览量', raw_data->>'页面浏览次数', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'pv') AS page_views_raw,
        COALESCE(raw_data->>'访客数', raw_data->>'独立访客', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv') AS unique_visitors_raw,
        semantic.resolve_alias(raw_data, data_domain, 'impressions', platform_code, granularity) AS impressions_raw,
        semantic.resolve_alias(raw_data, data_domain, 'clicks', platform_code, granularity) AS clicks_raw,
        semantic.resolve_alias(raw_data, data_domain, 'conversion_rate', platform_code, granularity) AS conversion_rate_raw,
        semantic.resolve_alias(raw_data, data_domain, 'order_count', platform_code, granularity) AS order_count_raw,
        semantic.resolve_alias(raw_data, data_domain, 'sales_amount', platform_code, granularity) AS sales_amount_raw,
        semantic.resolve_alias(raw_data, data_domain, 'sales_volume', platform_code, granularity) AS sales_volume_raw,
        -- 已下单口径(placed): 与已付款口径是**不同的业务事实**
        -- (实测两者销售额平均差 5.15%, 最大差 175.89) ⇒ 各自独立成列, 绝不互相冒充。
        -- 为什么必须并列: 实测 MYR/PHP 店铺(9208 行, 占 36%)的报表里**只有**
        -- 「已下 + 已确定」两套口径, 没有「已付款」列 ⇒ 只保留已付款口径会漏掉
        -- 三分之一的店铺的销售额(不是 0, 是**没这一口径**)。
        semantic.resolve_alias(raw_data, data_domain, 'order_count_placed', platform_code, granularity) AS order_count_placed_raw,
        semantic.resolve_alias(raw_data, data_domain, 'sales_amount_placed', platform_code, granularity) AS sales_amount_placed_raw,
        semantic.resolve_alias(raw_data, data_domain, 'sales_volume_placed', platform_code, granularity) AS sales_volume_placed_raw,
        semantic.resolve_alias(raw_data, data_domain, 'conversion_rate_placed', platform_code, granularity) AS conversion_rate_placed_raw,
        -- 行类别判定: shopee 商品报表是「商品汇总行 + SKU 明细行」两级结构。
        -- 汇总行的「规格编号」为 '-' 或空; 明细行有真实规格编号。
        -- 实测(shopee 商品月报 25809 行): 汇总行 11612 + 明细行 14197;
        -- 汇总行销售额 == 明细行之和(6258 组里 6217 组成立, 99.3%)
        -- ⇒ 汇总与明细同时计入 = 销售额翻倍。
        CASE
            WHEN COALESCE(raw_data->>'规格编号', '') IN ('', '-') THEN 'product_summary'
            ELSE 'sku_detail'
        END AS row_kind,
        COALESCE(raw_data->>'评价数', raw_data->>'评论数', raw_data->>'review_count', raw_data->>'Review Count', raw_data->>'reviews') AS review_count_raw,
        raw_data,
        header_columns,
        data_hash,
        ingest_timestamp,
        currency_code
    FROM raw_products
),
cleaned AS (
    SELECT
        platform_code,
        source_shop_id,
        identity_candidates,
        data_domain,
        granularity,
        metric_date,
        period_start_date,
        period_end_date,
        period_start_time,
        period_end_time,
        product_id,
        product_name,
        platform_sku,
        category,
        item_status,
        row_kind,
        CASE
            WHEN price_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(price_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(price_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS price,
        CASE
            WHEN stock_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(stock_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(stock_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS stock,
        CASE
            WHEN page_views_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(page_views_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(page_views_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS page_views,
        CASE
            WHEN unique_visitors_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(unique_visitors_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(unique_visitors_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS unique_visitors,
        CASE
            WHEN impressions_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(impressions_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(impressions_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS impressions,
        CASE
            WHEN clicks_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(clicks_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(clicks_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS clicks,
        CASE
            WHEN conversion_rate_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(conversion_rate_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(conversion_rate_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric / 100.0
            ELSE NULL
        END AS conversion_rate,
        CASE
            WHEN order_count_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(order_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(order_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS order_count,
        CASE
            WHEN sales_amount_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(sales_amount_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(sales_amount_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS sales_amount,
        CASE
            WHEN sales_volume_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(sales_volume_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(sales_volume_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS sales_volume,
        CASE
            WHEN review_count_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(review_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(review_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS review_count,
        CASE
            WHEN order_count_placed_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(order_count_placed_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(order_count_placed_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS order_count_placed,
        CASE
            WHEN sales_amount_placed_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(sales_amount_placed_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(sales_amount_placed_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS sales_amount_placed,
        CASE
            WHEN sales_volume_placed_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(sales_volume_placed_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(sales_volume_placed_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS sales_volume_placed,
        CASE
            WHEN conversion_rate_placed_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(conversion_rate_placed_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(conversion_rate_placed_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric / 100.0
            ELSE NULL
        END AS conversion_rate_placed,
        raw_data,
        header_columns,
        data_hash,
        ingest_timestamp,
        currency_code
    FROM mapped
),
deduplicated AS (
    -- 去重口径(2026-11-08 实测后重写):
    --
    -- 旧口径: PARTITION BY (platform, shop, data_hash) ⇒ 同一份报表被**反复采集**
    -- 时, 每次采集都有自己新的 data_hash ⇒ 一行都去不掉。
    -- 实测: 12122 个 (shop, period, sku) 组里 **3877 组重复**, 68% 的行落在重复组,
    -- 同一份内容最多有 10 个副本 ⇒ 订单数被放大 **2.67 倍**。
    --
    -- 新口径: 按**业务身份**去重, 而不是按 data_hash:
    --   PARTITION BY (platform, shop, granularity, 周期, 商品, 行类别内的规格)
    --   同一身份重复采集时取**最新**一份(最新 = 平台最后一次导出)。
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY
                platform_code,
                source_shop_id,
                granularity,
                COALESCE(period_start_date, metric_date),
                COALESCE(NULLIF(product_id, ''), data_hash),
                CASE
                    WHEN COALESCE(raw_data->>'规格编号', '') IN ('', '-') THEN ''
                    ELSE raw_data->>'规格编号'
                END
            ORDER BY ingest_timestamp DESC
        ) AS rn
    FROM cleaned
),
leveled AS (
    -- 汇总行优先: 同一 (平台, 店铺, 粒度, 周期, 商品) 下,
    -- 只要存在**商品汇总行**, 就只保留汇总行 —— 明细行是它的 SKU 拆分,
    -- 同时计入会让销售额翻倍(实测汇总行销售额 == 明细行之和, 99.3% 成立)。
    -- 没有汇总行的组(例如只有明细行)则原样保留全部明细行。
    SELECT
        d.*,
        MAX(
            CASE
                WHEN COALESCE(raw_data->>'规格编号', '') IN ('', '-') THEN 1
                ELSE NULL
            END
        ) OVER (
            PARTITION BY
                platform_code,
                source_shop_id,
                granularity,
                COALESCE(period_start_date, metric_date),
                COALESCE(NULLIF(product_id, ''), data_hash)
        ) AS group_has_summary
    FROM deduplicated d
    WHERE d.rn = 1
),
summary_only AS (
    -- 汇总行优先(接上过滤): 同一组里只要有商品汇总行, 就**只留汇总行**。
    -- 实测: 汇总行销售额 == 明细行之和(6258 组里 6217 组成立, 99.3%)
    -- ⇒ 两者同时进视图, 下游 SUM 会把销售额**翻倍**。
    -- 没有汇总行的组(只有明细行)则原样保留明细行。
    SELECT *
    FROM leveled
    WHERE group_has_summary IS NULL
       OR COALESCE(raw_data->>'规格编号', '') IN ('', '-')
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
    FROM summary_only d
    LEFT JOIN LATERAL (
        SELECT *
          FROM semantic.resolve_shop_identity(d.platform_code, d.identity_candidates, NULL)
    ) r ON TRUE
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
    product_id,
    product_name,
    platform_sku,
    category,
    item_status,
    -- ⚠ 这里**刻意不用 COALESCE(..., 0)**:
    --   COALESCE 把"没解析出来"伪装成"业务上真的是 0" ⇒ 解析缺失会静默失真。
    --   实测旧口径下 shopee 商品域 25809 行的标准字段全为空, 视图却显示 25809 个 0,
    --   没有任何告警 ⇒ 这就是"静默失真"的根因。
    --   现在: 解析不出来 = NULL(= unknown), 业务上真的是 0 = 0, 两者可区分。
    --   下游 `mart.product_day_kpi` 用 `COALESCE(sum(...), 0)` 聚合 ⇒ 行为不变。
    price,
    stock,
    page_views,
    unique_visitors,
    impressions,
    clicks,
    conversion_rate,
    order_count,
    sales_amount,
    sales_volume,
    review_count,
    raw_data,
    header_columns,
    data_hash,
    ingest_timestamp,
    currency_code,
    -- ↓ 新增列必须追加在末尾（CREATE OR REPLACE VIEW 不允许改变已有列的位置）
    -- 解析出的店铺账号ID（NULL = 没解析出来，键仍是原始标识）。
    resolved_shop_account_id,
    -- 身份候选数：0 = 没匹配到账号；1 = 唯一命中；>1 = 有歧义（已落 unknown）。
    identity_candidate_count,
    -- ↓ 新增列必须追加在末尾（CREATE OR REPLACE VIEW 不允许改变已有列的位置）
    -- ── 已下单口径(placed) ────────────────────────────────────────────
    -- 与上面的已付款口径是**不同的业务事实**, 绝不互相冒充。
    -- 必须并列的原因: MYR/PHP 店铺(9208 行, 36%)的报表里**没有**已付款口径列,
    -- 只有已下单口径 ⇒ 只留已付款口径会让这些店铺的销售额变成"没有数据"。
    order_count_placed,
    sales_amount_placed,
    sales_volume_placed,
    conversion_rate_placed,
    -- ── 行类别 ────────────────────────────────────────────────────────
    -- product_summary = 商品汇总行(已含其 SKU 明细之和)
    -- sku_detail      = SKU 明细行
    -- unknown         = 不是这两类(其它平台)
    CASE
        WHEN row_kind = 'product_summary' THEN 'product_summary'
        WHEN row_kind = 'sku_detail' THEN 'sku_detail'
        ELSE 'unknown'
    END AS row_kind,
    -- ── 解析状态 ──────────────────────────────────────────────────────
    -- ok         = 身份与核心指标都解析出来了
    -- partial    = 一部分解析出来了(缺个别指标)
    -- missing    = 有数据但核心指标一个都没解析出来
    -- empty_shell= 整行没有任何业务数据(raw_data 为空)
    CASE
        WHEN COALESCE(raw_data, '{}'::jsonb) = '{}'::jsonb THEN 'empty_shell'
        WHEN product_id IS NULL AND product_name IS NULL THEN 'missing'
        WHEN sales_amount IS NULL AND sales_amount_placed IS NULL
             AND order_count IS NULL AND order_count_placed IS NULL THEN 'partial'
        ELSE 'ok'
    END AS parse_status
FROM resolved;
