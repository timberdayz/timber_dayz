CREATE SCHEMA IF NOT EXISTS semantic;

DO $bootstrap$
BEGIN
    -- Prefer the materialized view when available (production path).
    IF EXISTS (
        SELECT 1
        FROM pg_matviews
        WHERE schemaname = 'semantic'
          AND matviewname = 'fact_orders_monthly_atomic_mv'
    ) THEN
        EXECUTE $view$
            CREATE OR REPLACE VIEW semantic.fact_orders_monthly_atomic AS
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
                paid_amount,
                product_quantity,
                profit,
                data_hash,
                ingest_timestamp
            FROM semantic.fact_orders_monthly_atomic_mv
        $view$;
    ELSE
        -- Fallback path for lightweight test containers where MV dependencies are not created.
        -- Keep base-table references in this file to make granularity contract checks explicit.
        EXECUTE $view$
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
                    metric_date::date AS metric_date,
                    platform_code,
                    NULLIF(TRIM(COALESCE(shop_id, '')), '') AS shop_id,
                    NULLIF(TRIM(COALESCE(shop_id, '')), '') AS raw_shop_id,
                    NULLIF(
                        TRIM(
                            COALESCE(
                                raw_data->>'store_name',
                                raw_data->>'store_label_raw',
                                raw_data->>'搴楅摵鍚嶇О',
                                raw_data->>'搴楅摵',
                                raw_data->>'搴楅摵鍚?'
                            )
                        ),
                        ''
                    ) AS store_label_raw,
                    NULL::text AS resolved_shop_account_id,
                    NULL::text AS resolution_method,
                    NULL::text AS identity_source_value,
                    NULLIF(TRIM(COALESCE(raw_data->>'order_id', raw_data->>'订单ID', raw_data->>'order')), '') AS order_id,
                    CASE
                        WHEN COALESCE(raw_data->>'paid_amount', raw_data->>'paid', raw_data->>'实付金额', raw_data->>'paidAmount') IS NULL THEN NULL
                        ELSE NULLIF(
                            REGEXP_REPLACE(
                                REPLACE(REPLACE(REPLACE(REPLACE(
                                    COALESCE(raw_data->>'paid_amount', raw_data->>'paid', raw_data->>'实付金额', raw_data->>'paidAmount'),
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
                        WHEN COALESCE(raw_data->>'product_quantity', raw_data->>'qty', raw_data->>'商品数量', raw_data->>'quantity') IS NULL THEN NULL
                        ELSE NULLIF(
                            REGEXP_REPLACE(
                                REPLACE(REPLACE(REPLACE(REPLACE(
                                    COALESCE(raw_data->>'product_quantity', raw_data->>'qty', raw_data->>'商品数量', raw_data->>'quantity'),
                                    ',', ''
                                ), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                                '[^0-9.-]',
                                '',
                                'g'
                            ),
                            ''
                        )::numeric
                    END AS product_quantity,
                    CASE
                        WHEN COALESCE(raw_data->>'profit', raw_data->>'盈利', raw_data->>'利润') IS NULL THEN NULL
                        ELSE NULLIF(
                            REGEXP_REPLACE(
                                REPLACE(REPLACE(REPLACE(REPLACE(
                                    COALESCE(raw_data->>'profit', raw_data->>'盈利', raw_data->>'利润'),
                                    ',', ''
                                ), ' ', ''), CHR(8212), ''), CHR(8211), ''),
                                '[^0-9.-]',
                                '',
                                'g'
                            ),
                            ''
                        )::numeric
                    END AS profit,
                    data_hash,
                    ingest_timestamp
                FROM raw_monthly_orders
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
                paid_amount,
                product_quantity,
                profit,
                data_hash,
                ingest_timestamp
            FROM mapped_monthly_orders
        $view$;
    END IF;
END
$bootstrap$;

