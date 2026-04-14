CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE VIEW mart.shop_month_kpi AS
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
                    REPLACE(
                        REPLACE(
                            REPLACE(
                                REPLACE(
                                    COALESCE(
                                        raw_data->>'实付金额',
                                        raw_data->>'买家实付金额',
                                        raw_data->>'总收入',
                                        raw_data->>'paid_amount',
                                        raw_data->>'Paid Amount'
                                    ),
                                    ',',
                                    ''
                                ),
                                ' ',
                                ''
                            ),
                            CHR(8212),
                            ''
                        ),
                        CHR(8211),
                        ''
                    ),
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
                    REPLACE(
                        REPLACE(
                            REPLACE(
                                REPLACE(
                                    COALESCE(
                                        raw_data->>'利润(RMB)',
                                        raw_data->>'profit_rmb',
                                        raw_data->>'利润',
                                        raw_data->>'profit',
                                        raw_data->>'毛利',
                                        raw_data->>'Profit'
                                    ),
                                    ',',
                                    ''
                                ),
                                ' ',
                                ''
                            ),
                            CHR(8212),
                            ''
                        ),
                        CHR(8211),
                        ''
                    ),
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
                    REPLACE(
                        REPLACE(
                            REPLACE(
                                REPLACE(
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
                                    ',',
                                    ''
                                ),
                                ' ',
                                ''
                            ),
                            CHR(8212),
                            ''
                        ),
                        CHR(8211),
                        ''
                    ),
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
),
resolved_monthly_orders AS (
    SELECT
        date_trunc('month', d.metric_date)::date AS period_month,
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
        d.profit
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
    WHERE d.rn = 1
),
monthly_orders AS (
    SELECT
        period_month,
        platform_code,
        shop_id,
        SUM(paid_amount) AS gmv,
        CASE
            WHEN COUNT(*) > 0 THEN COUNT(DISTINCT order_id)::numeric
            ELSE NULL
        END AS order_count,
        SUM(product_quantity) AS total_items,
        SUM(profit) AS profit,
        COUNT(*) AS source_row_count
    FROM resolved_monthly_orders
    GROUP BY period_month, platform_code, shop_id
),
raw_monthly_traffic AS (
    SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
    FROM b_class.fact_shopee_analytics_monthly
    UNION ALL
    SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
    FROM b_class.fact_tiktok_analytics_monthly
    UNION ALL
    SELECT platform_code, shop_id, metric_date, raw_data, data_hash, ingest_timestamp
    FROM b_class.fact_miaoshou_analytics_monthly
),
mapped_monthly_traffic AS (
    SELECT
        date_trunc('month', metric_date)::date AS period_month,
        platform_code,
        COALESCE(
            NULLIF(TRIM(COALESCE(shop_id, '')), ''),
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
            ),
            'unknown'
        ) AS shop_id,
        CASE
            WHEN COALESCE(
                raw_data->>'访客数',
                raw_data->>'独立访客',
                raw_data->>'去重页面浏览次数',
                raw_data->>'unique_visitors',
                raw_data->>'Unique Visitors',
                raw_data->>'uv',
                raw_data->>'visitor_count'
            ) IS NULL THEN NULL
            ELSE NULLIF(
                REGEXP_REPLACE(
                    REPLACE(
                        REPLACE(
                            REPLACE(
                                REPLACE(
                                    COALESCE(
                                        raw_data->>'访客数',
                                        raw_data->>'独立访客',
                                        raw_data->>'去重页面浏览次数',
                                        raw_data->>'unique_visitors',
                                        raw_data->>'Unique Visitors',
                                        raw_data->>'uv',
                                        raw_data->>'visitor_count'
                                    ),
                                    ',',
                                    ''
                                ),
                                ' ',
                                ''
                            ),
                            CHR(8212),
                            ''
                        ),
                        CHR(8211),
                        ''
                    ),
                    '[^0-9.-]',
                    '',
                    'g'
                ),
                ''
            )::numeric
        END AS visitor_count,
        CASE
            WHEN COALESCE(
                raw_data->>'浏览量',
                raw_data->>'页面浏览次数',
                raw_data->>'page_views',
                raw_data->>'Page Views',
                raw_data->>'views',
                raw_data->>'page_view'
            ) IS NULL THEN NULL
            ELSE NULLIF(
                REGEXP_REPLACE(
                    REPLACE(
                        REPLACE(
                            REPLACE(
                                REPLACE(
                                    COALESCE(
                                        raw_data->>'浏览量',
                                        raw_data->>'页面浏览次数',
                                        raw_data->>'page_views',
                                        raw_data->>'Page Views',
                                        raw_data->>'views',
                                        raw_data->>'page_view'
                                    ),
                                    ',',
                                    ''
                                ),
                                ' ',
                                ''
                            ),
                            CHR(8212),
                            ''
                        ),
                        CHR(8211),
                        ''
                    ),
                    '[^0-9.-]',
                    '',
                    'g'
                ),
                ''
            )::numeric
        END AS page_views,
        data_hash,
        ingest_timestamp
    FROM raw_monthly_traffic
),
deduplicated_monthly_traffic AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY platform_code, COALESCE(shop_id, ''), data_hash
            ORDER BY ingest_timestamp DESC
        ) AS rn
    FROM mapped_monthly_traffic
),
monthly_traffic AS (
    SELECT
        period_month,
        platform_code,
        shop_id,
        SUM(visitor_count) AS visitor_count,
        SUM(page_views) AS page_views,
        COUNT(*) AS source_row_count
    FROM deduplicated_monthly_traffic
    WHERE rn = 1
    GROUP BY period_month, platform_code, shop_id
)
SELECT
    COALESCE(o.period_month, t.period_month) AS period_month,
    COALESCE(o.platform_code, t.platform_code) AS platform_code,
    COALESCE(o.shop_id, t.shop_id) AS shop_id,
    CASE WHEN o.source_row_count > 0 THEN o.gmv END AS gmv,
    CASE WHEN o.source_row_count > 0 THEN o.order_count END AS order_count,
    CASE WHEN t.source_row_count > 0 THEN t.visitor_count END AS visitor_count,
    CASE WHEN t.source_row_count > 0 THEN t.page_views END AS page_views,
    CASE
        WHEN o.source_row_count > 0 AND t.source_row_count > 0 AND t.visitor_count > 0
        THEN ROUND(o.order_count * 100.0 / t.visitor_count, 2)
        WHEN o.source_row_count > 0 AND t.source_row_count > 0 AND t.visitor_count = 0 AND o.order_count = 0
        THEN 0
        ELSE NULL
    END AS conversion_rate,
    CASE
        WHEN o.source_row_count > 0 AND o.order_count > 0
        THEN ROUND(o.gmv::numeric / o.order_count, 2)
        WHEN o.source_row_count > 0 AND o.order_count = 0 AND o.gmv = 0
        THEN 0
        ELSE NULL
    END AS avg_order_value,
    CASE
        WHEN o.source_row_count > 0 AND o.order_count > 0
        THEN ROUND(o.total_items::numeric / o.order_count, 2)
        WHEN o.source_row_count > 0 AND o.order_count = 0 AND o.total_items = 0
        THEN 0
        ELSE NULL
    END AS attach_rate,
    CASE WHEN o.source_row_count > 0 THEN o.total_items END AS total_items,
    CASE WHEN o.source_row_count > 0 THEN o.profit END AS profit
FROM monthly_orders o
FULL OUTER JOIN monthly_traffic t
    ON o.period_month = t.period_month
   AND o.platform_code = t.platform_code
   AND COALESCE(o.shop_id, '') = COALESCE(t.shop_id, '');
