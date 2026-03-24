CREATE SCHEMA IF NOT EXISTS semantic;

CREATE OR REPLACE VIEW semantic.fact_orders_atomic AS
WITH raw_orders AS (
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_shopee_orders_daily
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_shopee_orders_weekly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_shopee_orders_monthly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_tiktok_orders_daily
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_tiktok_orders_weekly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_tiktok_orders_monthly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_miaoshou_orders_daily
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_miaoshou_orders_weekly
    UNION ALL
    SELECT platform_code, shop_id, data_domain, granularity, metric_date, period_start_date, period_end_date, period_start_time, period_end_time, raw_data, header_columns, data_hash, ingest_timestamp, currency_code
    FROM b_class.fact_miaoshou_orders_monthly
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
            )), '')
        ) AS shop_id,
        data_domain,
        granularity,
        metric_date::date AS metric_date,
        period_start_date::date AS period_start_date,
        period_end_date::date AS period_end_date,
        period_start_time,
        period_end_time,
        COALESCE(
            raw_data->>'订单号',
            raw_data->>'订单ID',
            raw_data->>'订单编号',
            raw_data->>'order_id',
            raw_data->>'Order ID',
            raw_data->>'order_no'
        ) AS order_id,
        COALESCE(
            raw_data->>'订单状态',
            raw_data->>'状态',
            raw_data->>'order_status',
            raw_data->>'Status'
        ) AS order_status,
        COALESCE(
            raw_data->>'销售额',
            raw_data->>'销售金额',
            raw_data->>'实付金额',
            raw_data->>'总收入',
            raw_data->>'GMV',
            raw_data->>'订单金额',
            raw_data->>'成交金额',
            raw_data->>'sales_amount',
            raw_data->>'Sales Amount'
        ) AS sales_amount_raw,
        COALESCE(
            raw_data->>'实付金额',
            raw_data->>'买家实付金额',
            raw_data->>'实付金额',
            raw_data->>'总收入',
            raw_data->>'paid_amount',
            raw_data->>'Paid Amount'
        ) AS paid_amount_raw,
        COALESCE(
            raw_data->>'利润',
            raw_data->>'profit',
            raw_data->>'毛利',
            raw_data->>'净利润',
            raw_data->>'Profit'
        ) AS profit_raw,
        COALESCE(
            raw_data->>'产品数量',
            raw_data->>'商品数量',
            raw_data->>'数量',
            raw_data->>'件数',
            raw_data->>'销售数量',
            raw_data->>'出库数量',
            raw_data->>'product_quantity',
            raw_data->>'quantity',
            raw_data->>'qty',
            raw_data->>'item_quantity'
        ) AS product_quantity_raw,
        COALESCE(
            raw_data->>'买家数',
            raw_data->>'买家',
            raw_data->>'buyer_count',
            raw_data->>'Buyer Count'
        ) AS buyer_count_raw,
        COALESCE(
            raw_data->>'产品ID',
            raw_data->>'商品ID',
            raw_data->>'product_id',
            raw_data->>'Product ID'
        ) AS product_id,
        COALESCE(
            raw_data->>'平台SKU',
            raw_data->>'platform_sku',
            raw_data->>'Platform SKU',
            raw_data->>'SKU'
        ) AS platform_sku,
        COALESCE(
            raw_data->>'SKU ID',
            raw_data->>'sku_id',
            raw_data->>'SKU_ID'
        ) AS sku_id,
        COALESCE(
            raw_data->>'商品SKU',
            raw_data->>'product_sku',
            raw_data->>'Product SKU',
            raw_data->>'商品货号'
        ) AS product_sku,
        COALESCE(
            raw_data->>'商品名称',
            raw_data->>'产品名称',
            raw_data->>'商品标题',
            raw_data->>'product_name',
            raw_data->>'Product Name'
        ) AS product_name,
        COALESCE(
            raw_data->>'下单时间',
            raw_data->>'订单时间',
            raw_data->>'order_time',
            raw_data->>'Order Time'
        ) AS order_time_raw,
        COALESCE(
            raw_data->>'付款时间',
            raw_data->>'支付时间',
            raw_data->>'payment_time',
            raw_data->>'Payment Time'
        ) AS payment_time_raw,
        raw_data,
        header_columns,
        data_hash,
        ingest_timestamp,
        currency_code
    FROM raw_orders
),
cleaned AS (
    SELECT
        platform_code,
        COALESCE(shop_id, 'unknown') AS shop_id,
        data_domain,
        granularity,
        metric_date,
        period_start_date,
        period_end_date,
        period_start_time,
        period_end_time,
        order_id,
        order_status,
        CASE
            WHEN sales_amount_raw IS NULL THEN NULL
            ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(sales_amount_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
        END AS sales_amount,
        CASE
            WHEN paid_amount_raw IS NULL THEN NULL
            ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(paid_amount_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
        END AS paid_amount,
        CASE
            WHEN profit_raw IS NULL THEN NULL
            ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(profit_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
        END AS profit,
        CASE
            WHEN product_quantity_raw IS NULL THEN NULL
            ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(product_quantity_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
        END AS product_quantity,
        CASE
            WHEN buyer_count_raw IS NULL THEN NULL
            ELSE NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(buyer_count_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
        END AS buyer_count,
        product_id,
        platform_sku,
        sku_id,
        product_sku,
        product_name,
        CASE
            WHEN order_time_raw IS NOT NULL AND order_time_raw <> '' THEN order_time_raw::timestamp
            ELSE NULL
        END AS order_time,
        CASE
            WHEN payment_time_raw IS NOT NULL AND payment_time_raw <> '' THEN payment_time_raw::timestamp
            ELSE NULL
        END AS payment_time,
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
    order_id,
    order_status,
    COALESCE(sales_amount, 0) AS sales_amount,
    COALESCE(paid_amount, 0) AS paid_amount,
    COALESCE(profit, 0) AS profit,
    COALESCE(product_quantity, 0) AS product_quantity,
    COALESCE(buyer_count, 0) AS buyer_count,
    0::numeric AS platform_total_cost_itemized,
    product_id,
    platform_sku,
    sku_id,
    product_sku,
    product_name,
    order_time,
    payment_time,
    COALESCE(period_start_date, metric_date) AS order_date,
    raw_data,
    header_columns,
    data_hash,
    ingest_timestamp,
    currency_code
FROM deduplicated
WHERE rn = 1;
