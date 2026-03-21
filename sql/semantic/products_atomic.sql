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
        COALESCE(NULLIF(TRIM(COALESCE(shop_id, '')), ''), 'unknown') AS shop_id,
        data_domain,
        granularity,
        metric_date::date AS metric_date,
        period_start_date::date AS period_start_date,
        period_end_date::date AS period_end_date,
        period_start_time,
        period_end_time,
        COALESCE(raw_data->>'商品ID', raw_data->>'产品ID', raw_data->>'product_id', raw_data->>'Product ID', raw_data->>'item_id') AS product_id,
        COALESCE(raw_data->>'商品名称', raw_data->>'产品名称', raw_data->>'商品标题', raw_data->>'product_name', raw_data->>'Product Name', raw_data->>'title') AS product_name,
        COALESCE(raw_data->>'平台SKU', raw_data->>'platform_sku', raw_data->>'Platform SKU', raw_data->>'SKU', raw_data->>'sku') AS platform_sku,
        COALESCE(raw_data->>'类目', raw_data->>'分类', raw_data->>'category', raw_data->>'Category') AS category,
        COALESCE(raw_data->>'商品状态', raw_data->>'状态', raw_data->>'item_status', raw_data->>'Item Status', raw_data->>'status') AS item_status,
        COALESCE(raw_data->>'价格', raw_data->>'单价', raw_data->>'售价', raw_data->>'price', raw_data->>'Price') AS price_raw,
        COALESCE(raw_data->>'库存', raw_data->>'库存数量', raw_data->>'stock', raw_data->>'Stock', raw_data->>'inventory') AS stock_raw,
        COALESCE(raw_data->>'浏览量', raw_data->>'页面浏览次数', raw_data->>'page_views', raw_data->>'Page Views', raw_data->>'views', raw_data->>'pv') AS page_views_raw,
        COALESCE(raw_data->>'访客数', raw_data->>'独立访客', raw_data->>'unique_visitors', raw_data->>'Unique Visitors', raw_data->>'uv') AS unique_visitors_raw,
        COALESCE(raw_data->>'曝光次数', raw_data->>'impressions', raw_data->>'Impressions') AS impressions_raw,
        COALESCE(raw_data->>'点击次数', raw_data->>'clicks', raw_data->>'Clicks') AS clicks_raw,
        COALESCE(raw_data->>'转化率', raw_data->>'conversion_rate', raw_data->>'Conversion Rate', raw_data->>'CVR') AS conversion_rate_raw,
        COALESCE(raw_data->>'订单数', raw_data->>'订单数量', raw_data->>'order_count', raw_data->>'Order Count', raw_data->>'orders') AS order_count_raw,
        COALESCE(raw_data->>'销售额', raw_data->>'销售金额', raw_data->>'sales_amount', raw_data->>'Sales Amount', raw_data->>'revenue') AS sales_amount_raw,
        COALESCE(raw_data->>'销量', raw_data->>'销售数量', raw_data->>'sales_volume', raw_data->>'Sales Volume', raw_data->>'qty') AS sales_volume_raw,
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
        CASE WHEN price_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(price_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric END AS price,
        CASE WHEN stock_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(stock_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric END AS stock,
        CASE WHEN page_views_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(page_views_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric END AS page_views,
        CASE WHEN unique_visitors_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(unique_visitors_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric END AS unique_visitors,
        CASE WHEN impressions_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(impressions_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric END AS impressions,
        CASE WHEN clicks_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(clicks_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric END AS clicks,
        CASE WHEN conversion_rate_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(conversion_rate_raw, '%', ''), ',', '.'), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric / 100.0 END AS conversion_rate,
        CASE WHEN order_count_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(order_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric END AS order_count,
        CASE WHEN sales_amount_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(sales_amount_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric END AS sales_amount,
        CASE WHEN sales_volume_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(sales_volume_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric END AS sales_volume,
        CASE WHEN review_count_raw IS NULL THEN NULL ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(review_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric END AS review_count,
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
    product_id,
    product_name,
    platform_sku,
    category,
    item_status,
    COALESCE(price, 0) AS price,
    COALESCE(stock, 0) AS stock,
    COALESCE(page_views, 0) AS page_views,
    COALESCE(unique_visitors, 0) AS unique_visitors,
    COALESCE(impressions, 0) AS impressions,
    COALESCE(clicks, 0) AS clicks,
    COALESCE(conversion_rate, 0) AS conversion_rate,
    COALESCE(order_count, 0) AS order_count,
    COALESCE(sales_amount, 0) AS sales_amount,
    COALESCE(sales_volume, 0) AS sales_volume,
    COALESCE(review_count, 0) AS review_count,
    raw_data,
    header_columns,
    data_hash,
    ingest_timestamp,
    currency_code
FROM deduplicated
WHERE rn = 1;
