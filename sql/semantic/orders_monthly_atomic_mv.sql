CREATE SCHEMA IF NOT EXISTS semantic;

DROP VIEW IF EXISTS semantic.fact_orders_monthly_atomic_mv;
DROP MATERIALIZED VIEW IF EXISTS semantic.fact_orders_monthly_atomic_mv;

CREATE MATERIALIZED VIEW semantic.fact_orders_monthly_atomic_mv AS
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
        COALESCE(
            raw_data->>'订单号',
            raw_data->>'订单ID',
            raw_data->>'订单编号',
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
resolved_monthly_orders AS (
    SELECT
        m.metric_date,
        m.platform_code,
        CASE
            WHEN resolved.resolved_shop_id IS NOT NULL THEN resolved.resolved_shop_id
            WHEN LOWER(COALESCE(m.source_shop_id, '')) IN ('', 'none', 'unknown', 'xihong') THEN 'unknown'
            ELSE COALESCE(m.source_platform_shop_id, m.source_shop_account_id, m.store_label_raw, m.source_shop_id, 'unknown')
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
        m.order_id,
        m.paid_amount,
        m.product_quantity,
        m.profit,
        m.data_hash,
        m.ingest_timestamp
    FROM mapped_monthly_orders m
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
deduplicated_monthly_orders AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY platform_code, COALESCE(shop_id, ''), data_hash
            ORDER BY ingest_timestamp DESC
        ) AS rn
    FROM resolved_monthly_orders
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
    order_id,
    COALESCE(paid_amount, 0) AS paid_amount,
    COALESCE(product_quantity, 0) AS product_quantity,
    COALESCE(profit, 0) AS profit,
    data_hash,
    ingest_timestamp
FROM deduplicated_monthly_orders
WHERE rn = 1;

CREATE INDEX IF NOT EXISTS ix_fact_orders_monthly_atomic_mv_period_platform_shop
ON semantic.fact_orders_monthly_atomic_mv (metric_date, platform_code, shop_id);

CREATE INDEX IF NOT EXISTS ix_fact_orders_monthly_atomic_mv_platform_shop_hash
ON semantic.fact_orders_monthly_atomic_mv (platform_code, shop_id, data_hash);
