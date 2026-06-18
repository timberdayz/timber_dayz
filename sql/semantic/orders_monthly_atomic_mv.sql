CREATE SCHEMA IF NOT EXISTS semantic;

-- Deploy-time bootstrap rebuilds the full dashboard pipeline. Dropping the MV with CASCADE is
-- acceptable here because downstream semantic/mart/api views will be recreated by the runner
-- in dependency order.
DROP MATERIALIZED VIEW IF EXISTS semantic.fact_orders_monthly_atomic_mv CASCADE;

CREATE MATERIALIZED VIEW semantic.fact_orders_monthly_atomic_mv AS
WITH raw_monthly_orders AS MATERIALIZED (
    SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
    FROM b_class.fact_shopee_orders_monthly
    UNION ALL
    SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
    FROM b_class.fact_tiktok_orders_monthly
    UNION ALL
    SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
    FROM b_class.fact_miaoshou_orders_monthly
),
mapped_monthly_orders AS MATERIALIZED (
    SELECT
        metric_date,
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
        COALESCE(
            NULLIF(TRIM(raw_data->>'下单时间'), ''),
            NULLIF(TRIM(raw_data->>'订单创建时间'), ''),
            NULLIF(TRIM(raw_data->>'create_time'), ''),
            NULLIF(TRIM(raw_data->>'order_create_time'), ''),
            NULLIF(TRIM(raw_data->>'order_time'), '')
        ) AS order_time_raw,
        COALESCE(
            raw_data->>'buyer_payment_rmb',
            raw_data->>'买家支付(RMB)',
            raw_data->>'买家实付金额_rmb',
            raw_data->>'买家实付金额(RMB)',
            raw_data->>'paid_amount_rmb',
            raw_data->>'实付金额_rmb',
            raw_data->>'实付金额(RMB)',
            raw_data->>'buyer_payment',
            raw_data->>'买家支付',
            raw_data->>'实付金额',
            raw_data->>'买家实付金额',
            raw_data->>'总收入',
            raw_data->>'paid_amount',
            raw_data->>'Paid Amount'
        ) AS paid_amount_raw,
        COALESCE(
            raw_data->>'利润(RMB)',
            raw_data->>'profit_rmb',
            raw_data->>'利润',
            raw_data->>'profit',
            raw_data->>'毛利',
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
        data_hash,
        ingest_timestamp
    FROM raw_monthly_orders
),
normalized_monthly_orders AS MATERIALIZED (
    SELECT
        COALESCE(
            date_trunc(
                'month',
                CASE
                    WHEN order_time_raw ~ '^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}'
                    THEN to_timestamp(order_time_raw, 'YYYY-MM-DD HH24:MI:SS')
                    WHEN order_time_raw ~ '^\d{4}-\d{2}-\d{2}$'
                    THEN to_date(order_time_raw, 'YYYY-MM-DD')::timestamp
                    ELSE metric_date::timestamp
                END
            )::date,
            date_trunc('month', metric_date)::date
        ) AS metric_date,
        platform_code,
        source_shop_id,
        store_label_raw,
        source_platform_shop_id,
        source_shop_account_id,
        order_id,
        CASE
            WHEN paid_amount_raw IS NULL THEN NULL
            ELSE NULLIF(
                REGEXP_REPLACE(
                    REPLACE(REPLACE(REPLACE(REPLACE(paid_amount_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                    '[^0-9.-]',
                    '',
                    'g'
                ),
                ''
            )::numeric
        END AS paid_amount,
        CASE
            WHEN profit_raw IS NULL THEN NULL
            ELSE NULLIF(
                REGEXP_REPLACE(
                    REPLACE(REPLACE(REPLACE(REPLACE(profit_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                    '[^0-9.-]',
                    '',
                    'g'
                ),
                ''
            )::numeric
        END AS profit,
        CASE
            WHEN product_quantity_raw IS NULL THEN NULL
            ELSE NULLIF(
                REGEXP_REPLACE(
                    REPLACE(REPLACE(REPLACE(REPLACE(product_quantity_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                    '[^0-9.-]',
                    '',
                    'g'
                ),
                ''
            )::numeric
        END AS product_quantity,
        LOWER(COALESCE(source_shop_id, '')) AS normalized_source_shop_id,
        LOWER(COALESCE(source_platform_shop_id, '')) AS normalized_source_platform_shop_id,
        LOWER(COALESCE(source_shop_account_id, '')) AS normalized_source_shop_account_id,
        REGEXP_REPLACE(
            REGEXP_REPLACE(
                LOWER(TRIM(COALESCE(source_shop_id, ''))),
                '^(shopee|tiktok\s*shop|tiktok|tk|miaoshou|amazon|lazada)\s*',
                '',
                'i'
            ),
            '[[:space:]_()/-]+',
            '',
            'g'
        ) AS normalized_source_shop_id_compact,
        REGEXP_REPLACE(
            REGEXP_REPLACE(
                LOWER(TRIM(COALESCE(store_label_raw, ''))),
                '^(shopee|tiktok\s*shop|tiktok|tk|miaoshou|amazon|lazada)\s*',
                '',
                'i'
            ),
            '[[:space:]_()/-]+',
            '',
            'g'
        ) AS normalized_store_label_raw,
        data_hash,
        ingest_timestamp
    FROM mapped_monthly_orders
),
prepared_identity_monthly_orders AS MATERIALIZED (
    SELECT
        n.*,
        ARRAY_REMOVE(
            ARRAY[
                n.normalized_source_platform_shop_id,
                n.normalized_source_shop_account_id,
                CASE
                    WHEN n.normalized_source_shop_id NOT IN ('xihong', 'unknown', 'none')
                    THEN n.normalized_source_shop_id
                END,
                CASE
                    WHEN n.normalized_source_shop_id NOT IN ('xihong', 'unknown', 'none')
                    THEN n.normalized_source_shop_id_compact
                END,
                n.normalized_store_label_raw
            ],
            ''
        ) AS normalized_identity_candidates
    FROM normalized_monthly_orders n
),
resolved_monthly_orders AS MATERIALIZED (
    SELECT
        m.metric_date,
        m.platform_code,
        CASE
            WHEN resolved.resolved_shop_id IS NOT NULL
            THEN COALESCE(NULLIF(TRIM(canonical.platform_shop_id), ''), resolved.resolved_shop_id)
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
        CASE
            WHEN resolved.resolved_shop_id IS NOT NULL THEN resolved.identity_source_value
            ELSE COALESCE(m.source_platform_shop_id, m.source_shop_account_id, m.store_label_raw, m.source_shop_id)
        END AS identity_source_value,
        CASE
            WHEN resolved.resolved_shop_account_id IS NOT NULL
            THEN COALESCE(NULLIF(TRIM(canonical.platform_shop_id), ''), resolved.resolved_shop_id)
        END AS canonical_shop_id,
        CASE
            WHEN COALESCE(m.source_platform_shop_id, m.source_shop_account_id, m.store_label_raw, m.source_shop_id) IS NULL
            THEN 'missing_identity'
            WHEN resolved.resolved_shop_account_id IS NULL
            THEN 'unresolved_shop_account'
            WHEN resolved.resolved_shop_account_id IS NOT NULL AND canonical.shop_account_id IS NULL
            THEN 'unresolved_shop_account'
            WHEN resolved.resolved_shop_account_id IS NOT NULL
             AND LOWER(COALESCE(m.platform_code, '')) IN ('shopee')
             AND NULLIF(TRIM(canonical.platform_shop_id), '') IS NULL
            THEN 'missing_required_platform_shop_id'
            ELSE NULL
        END AS identity_warning_code,
        m.order_id,
        m.paid_amount,
        m.product_quantity,
        m.profit,
        m.data_hash,
        m.ingest_timestamp
    FROM prepared_identity_monthly_orders m
    LEFT JOIN LATERAL (
        SELECT
            c.resolved_shop_id,
            c.resolved_shop_account_id,
            c.resolution_method,
            c.resolution_priority,
            c.identity_source_value
        FROM semantic.shop_identity_resolution_candidates c
        WHERE c.platform_code = LOWER(COALESCE(m.platform_code, ''))
          AND c.identity_value_normalized = ANY (m.normalized_identity_candidates)
        ORDER BY c.resolution_priority, c.resolved_shop_id
        LIMIT 1
    ) resolved ON TRUE
    LEFT JOIN core.shop_accounts canonical
      ON LOWER(COALESCE(canonical.platform, '')) = LOWER(COALESCE(m.platform_code, ''))
     AND canonical.shop_account_id = resolved.resolved_shop_account_id
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
    canonical_shop_id,
    identity_warning_code,
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
