CREATE SCHEMA IF NOT EXISTS semantic;

CREATE OR REPLACE VIEW semantic.fact_orders_monthly_atomic AS
WITH raw_monthly_orders AS (
    SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
    FROM b_class.fact_shopee_orders_monthly
    UNION ALL
    SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
    FROM b_class.fact_tiktok_orders_monthly
    UNION ALL
    SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
    FROM b_class.fact_miaoshou_orders_monthly
),
mapped_monthly_orders AS (
    SELECT
        platform_code,
        NULLIF(TRIM(COALESCE(shop_id, '')), '') AS source_shop_id,
        NULLIF(
            TRIM(
                COALESCE(
                    raw_data->>'店铺',
                    raw_data->>'店铺名',
                    raw_data->>'店铺名称',
                    raw_data->>'店铺',
                    raw_data->>'店铺名',
                    raw_data->>'店铺名称',
                    raw_data->>'store_name',
                    raw_data->>'store_label_raw'
                )
            ),
            ''
        ) AS store_label_raw,
        metric_date::date AS metric_date,
        COALESCE(
            raw_data->>'订单号',
            raw_data->>'订单ID',
            raw_data->>'订单编号',
            raw_data->>'订单编号',
            raw_data->>'订单号',
            raw_data->>'ID',
            raw_data->>'order_id',
            raw_data->>'Order ID',
            raw_data->>'order_no'
        ) AS order_id,
        CASE
            WHEN COALESCE(
                raw_data->>'实付金额',
                raw_data->>'买家实付金额',
                raw_data->>'总收入',
                raw_data->>'buyer_payment_rmb',
                raw_data->>'buyer_payment',
                raw_data->>'买家支付(RMB)',
                raw_data->>'买家支付',
                raw_data->>'买家实付金额(RMB)',
                raw_data->>'paid_amount',
                raw_data->>'Paid Amount'
            ) IS NULL THEN NULL
            ELSE NULLIF(
                REGEXP_REPLACE(
                    REPLACE(REPLACE(REPLACE(REPLACE(
                        COALESCE(
                            raw_data->>'实付金额',
                            raw_data->>'买家实付金额',
                            raw_data->>'总收入',
                            raw_data->>'buyer_payment_rmb',
                            raw_data->>'buyer_payment',
                            raw_data->>'买家支付(RMB)',
                            raw_data->>'买家支付',
                            raw_data->>'买家实付金额(RMB)',
                            raw_data->>'paid_amount',
                            raw_data->>'Paid Amount'
                        ),
                        ',', ''
                    ), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                    '[^0-9.-]',
                    '',
                    'g'
                ),
                ''
            )::numeric
        END AS paid_amount,
        CASE
            WHEN COALESCE(
                raw_data->>'利润(RMB)',
                raw_data->>'profit_rmb',
                raw_data->>'利润',
                raw_data->>'profit',
                raw_data->>'毛利',
                raw_data->>'Profit'
            ) IS NULL THEN NULL
            ELSE NULLIF(
                REGEXP_REPLACE(
                    REPLACE(REPLACE(REPLACE(REPLACE(
                        COALESCE(
                            raw_data->>'利润(RMB)',
                            raw_data->>'profit_rmb',
                            raw_data->>'利润',
                            raw_data->>'profit',
                            raw_data->>'毛利',
                            raw_data->>'Profit'
                        ),
                        ',', ''
                    ), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                    '[^0-9.-]',
                    '',
                    'g'
                ),
                ''
            )::numeric
        END AS profit,
        CASE
            WHEN COALESCE(
                raw_data->>'original_amount_rmb',
                raw_data->>'original_amount',
                raw_data->>'order_original_amount_rmb',
                raw_data->>'product_original_price_rmb',
                raw_data->>'product_original_price',
                raw_data->>'订单原始金额(RMB)',
                raw_data->>'产品原价(RMB)',
                raw_data->>'订单原始金额',
                raw_data->>'产品原价',
                raw_data->>'order_original_amount'
            ) IS NULL THEN NULL
            ELSE NULLIF(
                REGEXP_REPLACE(
                    REPLACE(REPLACE(REPLACE(REPLACE(
                        COALESCE(
                            raw_data->>'original_amount_rmb',
                            raw_data->>'original_amount',
                            raw_data->>'order_original_amount_rmb',
                            raw_data->>'product_original_price_rmb',
                            raw_data->>'product_original_price',
                            raw_data->>'订单原始金额(RMB)',
                            raw_data->>'产品原价(RMB)',
                            raw_data->>'订单原始金额',
                            raw_data->>'产品原价',
                            raw_data->>'order_original_amount'
                        ),
                        ',', ''
                    ), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                    '[^0-9.-]',
                    '',
                    'g'
                ),
                ''
            )::numeric
        END AS order_original_amount,
        CASE
            WHEN COALESCE(
                raw_data->>'purchase_amount_rmb',
                raw_data->>'purchase_cost_rmb',
                raw_data->>'procurement_cost_rmb',
                raw_data->>'采购成本(RMB)',
                raw_data->>'采购成本',
                raw_data->>'采购金额(RMB)',
                raw_data->>'purchase_amount',
                raw_data->>'purchase_cost',
                raw_data->>'procurement_cost'
            ) IS NULL THEN NULL
            ELSE NULLIF(
                REGEXP_REPLACE(
                    REPLACE(REPLACE(REPLACE(REPLACE(
                        COALESCE(
                            raw_data->>'purchase_amount_rmb',
                            raw_data->>'purchase_cost_rmb',
                            raw_data->>'procurement_cost_rmb',
                            raw_data->>'采购成本(RMB)',
                            raw_data->>'采购成本',
                            raw_data->>'采购金额(RMB)',
                            raw_data->>'purchase_amount',
                            raw_data->>'purchase_cost',
                            raw_data->>'procurement_cost'
                        ),
                        ',', ''
                    ), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                    '[^0-9.-]',
                    '',
                    'g'
                ),
                ''
            )::numeric
        END AS purchase_amount,
        CASE
            WHEN COALESCE(
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
            ) IS NULL THEN NULL
            ELSE NULLIF(
                REGEXP_REPLACE(
                    REPLACE(REPLACE(REPLACE(REPLACE(
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
                        ),
                        ',', ''
                    ), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                    '[^0-9.-]',
                    '',
                    'g'
                ),
                ''
            )::numeric
        END AS product_quantity,
        data_hash,
        ingest_timestamp
    FROM raw_monthly_orders
),
deduplicated_monthly_orders AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY platform_code, COALESCE(source_shop_id, ''), data_hash
            ORDER BY ingest_timestamp DESC
        ) AS rn
    FROM mapped_monthly_orders
)
SELECT
    date_trunc('month', d.metric_date)::date AS metric_date,
    d.platform_code,
    CASE
        WHEN pa.resolved_shop_id IS NOT NULL THEN pa.resolved_shop_id
        WHEN LOWER(COALESCE(d.source_shop_id, '')) IN ('', 'none', 'unknown', 'xihong')
        THEN 'unknown'
        ELSE COALESCE(d.source_shop_id, 'unknown')
    END AS shop_id,
    d.order_id,
    d.paid_amount,
    d.product_quantity,
    d.profit,
    d.data_hash,
    d.ingest_timestamp
FROM deduplicated_monthly_orders d
LEFT JOIN LATERAL (
    SELECT
        COALESCE(
            NULLIF(TRIM(sa.platform_shop_id), ''),
            NULLIF(TRIM(sa.shop_account_id), ''),
            sa.id::text
        ) AS resolved_shop_id
    FROM core.shop_accounts sa
    LEFT JOIN core.shop_account_aliases saa
      ON saa.shop_account_id = sa.id
     AND saa.is_active = true
    WHERE LOWER(COALESCE(sa.platform, '')) = LOWER(COALESCE(d.platform_code, ''))
      AND (
          LOWER(COALESCE(sa.store_name, '')) = LOWER(COALESCE(d.store_label_raw, ''))
          OR LOWER(COALESCE(sa.platform_shop_id, '')) = LOWER(COALESCE(d.store_label_raw, ''))
          OR LOWER(COALESCE(saa.alias_value, '')) = LOWER(COALESCE(d.store_label_raw, ''))
          OR LOWER(COALESCE(saa.alias_normalized, '')) = REGEXP_REPLACE(REGEXP_REPLACE(LOWER(TRIM(COALESCE(d.store_label_raw, ''))), '^(shopee|tiktok\s*shop|tiktok|tk|miaoshou|amazon|lazada)\s*', '', 'i'), '\s+', ' ', 'g')
      )
    ORDER BY
        CASE WHEN LOWER(COALESCE(saa.alias_normalized, '')) = REGEXP_REPLACE(REGEXP_REPLACE(LOWER(TRIM(COALESCE(d.store_label_raw, ''))), '^(shopee|tiktok\s*shop|tiktok|tk|miaoshou|amazon|lazada)\s*', '', 'i'), '\s+', ' ', 'g') THEN 0 ELSE 1 END,
        CASE WHEN saa.is_primary THEN 0 ELSE 1 END,
        sa.id
    LIMIT 1
) pa ON TRUE
WHERE d.rn = 1;
