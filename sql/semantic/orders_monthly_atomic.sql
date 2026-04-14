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
            raw_data->>'order_id',
            raw_data->>'Order ID',
            raw_data->>'order_no'
        ) AS order_id,
        CASE
            WHEN COALESCE(
                raw_data->>'实付金额',
                raw_data->>'买家实付金额',
                raw_data->>'总收入',
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
        WHEN (
            COALESCE(NULLIF(TRIM(pa.shop_id), ''), NULLIF(TRIM(pa.account_id), '')) IS NOT NULL
            AND (
                d.source_shop_id IS NULL
                OR LOWER(d.source_shop_id) IN ('none', 'unknown')
                OR (d.store_label_raw IS NOT NULL AND LOWER(d.source_shop_id) = LOWER(d.store_label_raw))
            )
        )
        THEN COALESCE(NULLIF(TRIM(pa.shop_id), ''), NULLIF(TRIM(pa.account_id), ''))
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
        COALESCE(NULLIF(TRIM(pa_inner.shop_id), ''), NULLIF(TRIM(pa_inner.account_id), '')) AS shop_id,
        pa_inner.account_id
    FROM core.platform_accounts pa_inner
    WHERE LOWER(COALESCE(pa_inner.platform, '')) = LOWER(COALESCE(d.platform_code, ''))
      AND (
          LOWER(COALESCE(pa_inner.account_alias, '')) = LOWER(COALESCE(d.store_label_raw, ''))
          OR LOWER(COALESCE(pa_inner.store_name, '')) = LOWER(COALESCE(d.store_label_raw, ''))
      )
    ORDER BY
        CASE WHEN LOWER(COALESCE(pa_inner.account_alias, '')) = LOWER(COALESCE(d.store_label_raw, '')) THEN 0 ELSE 1 END,
        pa_inner.id
    LIMIT 1
) pa ON TRUE
WHERE d.rn = 1;
