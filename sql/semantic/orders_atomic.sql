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
                    raw_data->>'采购账号',
                    raw_data->>'账号',
                    raw_data->>'account',
                    raw_data->>'account_alias'
                )
            ),
            ''
        ) AS source_account,
        NULLIF(TRIM(COALESCE(raw_data->>'站点', raw_data->>'site')), '') AS source_site,
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
            NULLIF(TRIM(raw_data->>'采购金额'), ''),
            NULLIF(TRIM(raw_data->>'采购价'), ''),
            NULLIF(TRIM(raw_data->>'产品成本'), ''),
            NULLIF(TRIM(raw_data->>'cogs'), ''),
            NULLIF(TRIM(raw_data->>'purchase_amount'), ''),
            NULLIF(TRIM(raw_data->>'Purchase Amount'), ''),
            NULLIF(TRIM(raw_data->>'purchase_cost'), ''),
            NULLIF(TRIM(raw_data->>'procurement_cost'), '')
        ) AS purchase_amount_raw,
        COALESCE(
            NULLIF(TRIM(raw_data->>'订单原始金额'), ''),
            NULLIF(TRIM(raw_data->>'产品折后价格'), ''),
            NULLIF(TRIM(raw_data->>'产品折后金额'), ''),
            NULLIF(TRIM(raw_data->>'产品原价'), ''),
            NULLIF(TRIM(raw_data->>'order_original_amount'), ''),
            NULLIF(TRIM(raw_data->>'Order Original Amount'), ''),
            NULLIF(TRIM(raw_data->>'original_order_amount'), ''),
            NULLIF(TRIM(raw_data->>'order_amount'), '')
        ) AS order_original_amount_raw,
        COALESCE(
            NULLIF(TRIM(raw_data->>'仓库操作费'), ''),
            NULLIF(TRIM(raw_data->>'贴单费'), ''),
            NULLIF(TRIM(raw_data->>'warehouse_operation_fee'), ''),
            NULLIF(TRIM(raw_data->>'Warehouse Operation Fee'), ''),
            NULLIF(TRIM(raw_data->>'warehouse_fee'), '')
        ) AS warehouse_operation_fee_raw,
        COALESCE(
            NULLIF(TRIM(raw_data->>'运费'), ''),
            NULLIF(TRIM(raw_data->>'商家运费'), ''),
            NULLIF(TRIM(raw_data->>'shipping_fee'), ''),
            NULLIF(TRIM(raw_data->>'Shipping Fee'), ''),
            NULLIF(TRIM(raw_data->>'logistics_fee'), '')
        ) AS shipping_fee_raw,
        COALESCE(
            NULLIF(TRIM(raw_data->>'推广费'), ''),
            NULLIF(TRIM(raw_data->>'平台推广费'), ''),
            NULLIF(TRIM(raw_data->>'平台收取推广费'), ''),
            NULLIF(TRIM(raw_data->>'营销推广费'), ''),
            NULLIF(TRIM(raw_data->>'promotion_fee'), ''),
            NULLIF(TRIM(raw_data->>'Promotion Fee'), ''),
            NULLIF(TRIM(raw_data->>'campaign_fee'), '')
        ) AS promotion_fee_raw,
        COALESCE(
            NULLIF(TRIM(raw_data->>'平台佣金'), ''),
            NULLIF(TRIM(raw_data->>'佣金'), ''),
            NULLIF(TRIM(raw_data->>'总佣金'), ''),
            NULLIF(TRIM(raw_data->>'TikTok Shop平台佣金'), ''),
            NULLIF(TRIM(raw_data->>'platform_commission'), ''),
            NULLIF(TRIM(raw_data->>'Platform Commission'), ''),
            NULLIF(TRIM(raw_data->>'commission_fee'), '')
        ) AS platform_commission_raw,
        COALESCE(
            NULLIF(TRIM(raw_data->>'平台扣费'), ''),
            NULLIF(TRIM(raw_data->>'平台扣款'), ''),
            NULLIF(TRIM(raw_data->>'TikTok Shop平台扣费'), ''),
            NULLIF(TRIM(raw_data->>'platform_deduction_fee'), ''),
            NULLIF(TRIM(raw_data->>'Platform Deduction Fee'), ''),
            NULLIF(TRIM(raw_data->>'deduction_fee'), '')
        ) AS platform_deduction_fee_raw,
        COALESCE(
            NULLIF(TRIM(raw_data->>'代金券'), ''),
            NULLIF(TRIM(raw_data->>'平台代金券'), ''),
            NULLIF(TRIM(raw_data->>'平台优惠券'), ''),
            NULLIF(TRIM(raw_data->>'platform_voucher'), ''),
            NULLIF(TRIM(raw_data->>'Platform Voucher'), ''),
            NULLIF(TRIM(raw_data->>'voucher_amount'), '')
        ) AS platform_voucher_raw,
        COALESCE(
            NULLIF(TRIM(raw_data->>'服务费'), ''),
            NULLIF(TRIM(raw_data->>'平台服务费'), ''),
            NULLIF(TRIM(raw_data->>'平台收取服务费'), ''),
            NULLIF(TRIM(raw_data->>'TikTok Shop平台服务费'), ''),
            NULLIF(TRIM(raw_data->>'platform_service_fee'), ''),
            NULLIF(TRIM(raw_data->>'Platform Service Fee'), ''),
            NULLIF(TRIM(raw_data->>'service_fee'), '')
        ) AS platform_service_fee_raw,
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
        COALESCE(source_shop_id, 'unknown') AS shop_id,
        store_label_raw,
        source_account,
        source_site,
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
            WHEN purchase_amount_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(purchase_amount_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(purchase_amount_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS purchase_amount,
        CASE
            WHEN order_original_amount_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(order_original_amount_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(order_original_amount_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS order_original_amount,
        CASE
            WHEN warehouse_operation_fee_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(warehouse_operation_fee_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(warehouse_operation_fee_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS warehouse_operation_fee,
        CASE
            WHEN shipping_fee_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(shipping_fee_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(shipping_fee_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS shipping_fee,
        CASE
            WHEN promotion_fee_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(promotion_fee_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(promotion_fee_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS promotion_fee,
        CASE
            WHEN platform_commission_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(platform_commission_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(platform_commission_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS platform_commission,
        CASE
            WHEN platform_deduction_fee_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(platform_deduction_fee_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(platform_deduction_fee_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS platform_deduction_fee,
        CASE
            WHEN platform_voucher_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(platform_voucher_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(platform_voucher_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS platform_voucher,
        CASE
            WHEN platform_service_fee_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(platform_service_fee_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(platform_service_fee_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS platform_service_fee,
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
),
alias_resolved AS (
    SELECT
        d.platform_code,
        CASE
            WHEN account_map.resolved_shop_id IS NOT NULL
                 AND (
                    d.shop_id IS NULL
                    OR LOWER(d.shop_id) IN ('none', 'unknown')
                    OR (d.store_label_raw IS NOT NULL AND LOWER(d.shop_id) = LOWER(d.store_label_raw))
                 )
            THEN account_map.resolved_shop_id
            ELSE COALESCE(d.shop_id, 'unknown')
        END AS shop_id,
        d.data_domain,
        d.granularity,
        d.metric_date,
        d.period_start_date,
        d.period_end_date,
        d.period_start_time,
        d.period_end_time,
        d.order_id,
        d.order_status,
        d.sales_amount,
        d.paid_amount,
        d.profit,
        d.purchase_amount,
        d.order_original_amount,
        d.warehouse_operation_fee,
        d.shipping_fee,
        d.promotion_fee,
        d.platform_commission,
        d.platform_deduction_fee,
        d.platform_voucher,
        d.platform_service_fee,
        d.product_quantity,
        d.buyer_count,
        d.product_id,
        d.platform_sku,
        d.sku_id,
        d.product_sku,
        d.product_name,
        d.order_time,
        d.payment_time,
        d.raw_data,
        d.header_columns,
        d.data_hash,
        d.ingest_timestamp,
        d.currency_code
    FROM deduplicated d
    LEFT JOIN LATERAL (
        SELECT
            COALESCE(NULLIF(TRIM(pa.shop_id), ''), NULLIF(TRIM(pa.account_id), '')) AS resolved_shop_id
        FROM core.platform_accounts pa
        WHERE LOWER(COALESCE(pa.platform, '')) = LOWER(COALESCE(d.platform_code, ''))
          AND (
                LOWER(COALESCE(pa.account_alias, '')) = LOWER(COALESCE(d.store_label_raw, ''))
                OR LOWER(COALESCE(pa.store_name, '')) = LOWER(COALESCE(d.store_label_raw, ''))
          )
        ORDER BY
            CASE WHEN LOWER(COALESCE(pa.account_alias, '')) = LOWER(COALESCE(d.store_label_raw, '')) THEN 0 ELSE 1 END,
            pa.id
        LIMIT 1
    ) account_map ON TRUE
    WHERE d.rn = 1
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
    purchase_amount,
    order_original_amount,
    warehouse_operation_fee,
    shipping_fee,
    promotion_fee,
    platform_commission,
    platform_deduction_fee,
    platform_voucher,
    platform_service_fee,
    COALESCE(product_quantity, 0) AS product_quantity,
    COALESCE(buyer_count, 0) AS buyer_count,
    (
        COALESCE(shipping_fee, 0)
        + COALESCE(promotion_fee, 0)
        + COALESCE(platform_commission, 0)
        + COALESCE(platform_deduction_fee, 0)
        + COALESCE(platform_voucher, 0)
        + COALESCE(platform_service_fee, 0)
    ) AS platform_total_cost_itemized,
    (
        order_original_amount
        - purchase_amount
        - profit
        - warehouse_operation_fee
    ) AS platform_total_cost_derived,
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
FROM alias_resolved;
