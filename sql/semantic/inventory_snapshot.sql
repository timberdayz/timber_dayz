CREATE SCHEMA IF NOT EXISTS semantic;

CREATE OR REPLACE VIEW semantic.fact_inventory_snapshot AS
WITH raw_inventory AS (
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
        file_id,
        raw_data,
        header_columns,
        data_hash,
        ingest_timestamp,
        currency_code
    FROM b_class.fact_shopee_inventory_snapshot

    UNION ALL

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
        file_id,
        raw_data,
        header_columns,
        data_hash,
        ingest_timestamp,
        currency_code
    FROM b_class.fact_tiktok_inventory_snapshot

    UNION ALL

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
        file_id,
        raw_data,
        header_columns,
        data_hash,
        ingest_timestamp,
        currency_code
    FROM b_class.fact_miaoshou_inventory_snapshot
),
mapped AS (
    SELECT
        platform_code,
        COALESCE(
            NULLIF(TRIM(COALESCE(shop_id, '')), ''),
            NULLIF(TRIM(COALESCE(raw_data->>'shop_id', '')), ''),
            'unknown'
        ) AS shop_id,
        data_domain,
        granularity,
        metric_date::date AS metric_date,
        period_start_date::date AS period_start_date,
        period_end_date::date AS period_end_date,
        period_start_time,
        period_end_time,
        file_id,
        COALESCE(
            raw_data->>'商品ID',
            raw_data->>'产品ID',
            raw_data->>'*商品ID',
            raw_data->>'product_id',
            raw_data->>'Product ID',
            raw_data->>'item_id'
        ) AS product_id,
        COALESCE(
            raw_data->>'商品名称',
            raw_data->>'产品名称',
            raw_data->>'商品标题',
            raw_data->>'*商品名称',
            raw_data->>'product_name',
            raw_data->>'Product Name',
            raw_data->>'title'
        ) AS product_name,
        COALESCE(
            raw_data->>'平台SKU',
            raw_data->>'*商品SKU',
            raw_data->>'*商品',
            raw_data->>'platform_sku',
            raw_data->>'Platform SKU',
            raw_data->>'SKU',
            raw_data->>'sku'
        ) AS platform_sku,
        COALESCE(
            raw_data->>'SKU ID',
            raw_data->>'sku_id',
            raw_data->>'SKU_ID'
        ) AS sku_id,
        COALESCE(
            raw_data->>'商品SKU',
            raw_data->>'*商品SKU',
            raw_data->>'*商品',
            raw_data->>'product_sku',
            raw_data->>'Product SKU',
            raw_data->>'商品货号'
        ) AS product_sku,
        COALESCE(
            raw_data->>'仓库',
            raw_data->>'仓库名称',
            raw_data->>'warehouse',
            raw_data->>'Warehouse',
            raw_data->>'warehouse_name'
        ) AS warehouse_name,
        COALESCE(
            raw_data->>'仓库编码',
            raw_data->>'warehouse_code',
            raw_data->>'Warehouse Code'
        ) AS warehouse_code,
        COALESCE(
            raw_data->>'可用库存',
            raw_data->>'available_stock',
            raw_data->>'Available Stock',
            raw_data->>'available'
        ) AS available_stock_raw,
        COALESCE(
            raw_data->>'在库库存',
            raw_data->>'库存总量',
            raw_data->>'on_hand_stock',
            raw_data->>'On Hand Stock',
            raw_data->>'on_hand'
        ) AS on_hand_stock_raw,
        COALESCE(
            raw_data->>'锁定库存',
            raw_data->>'预占库存',
            raw_data->>'reserved_stock',
            raw_data->>'Reserved Stock',
            raw_data->>'reserved'
        ) AS reserved_stock_raw,
        COALESCE(
            raw_data->>'在途库存',
            raw_data->>'in_transit_stock',
            raw_data->>'In Transit Stock',
            raw_data->>'in_transit'
        ) AS in_transit_stock_raw,
        COALESCE(
            raw_data->>'缺货数量',
            raw_data->>'stockout_qty',
            raw_data->>'Stockout Qty',
            raw_data->>'stockout'
        ) AS stockout_qty_raw,
        COALESCE(
            raw_data->>'补货点',
            raw_data->>'reorder_point',
            raw_data->>'Reorder Point'
        ) AS reorder_point_raw,
        COALESCE(
            raw_data->>'安全库存',
            raw_data->>'Safety Stock',
            raw_data->>'safety_stock'
        ) AS safety_stock_raw,
        COALESCE(
            raw_data->>'成本',
            raw_data->>'成本价',
            raw_data->>E'*单价\n（元）',
            raw_data->>'单价',
            raw_data->>'cost',
            raw_data->>'Cost',
            raw_data->>'unit_cost'
        ) AS unit_cost_raw,
        COALESCE(
            raw_data->>'库存金额',
            raw_data->>'库存价值',
            raw_data->>E'*总价\n（元）',
            raw_data->>'总价',
            raw_data->>'inventory_value',
            raw_data->>'Inventory Value'
        ) AS inventory_value_raw,
        -- 行级时间戳：妙手「更新时间 / 创建时间」是北京时间墙上时间，
        -- 必须显式按 Asia/Shanghai 解释（数据库会话时区是 UTC）。
        NULLIF(BTRIM(raw_data->>'更新时间'), '') AS observed_at_raw,
        NULLIF(BTRIM(raw_data->>'创建时间'), '') AS created_at_raw,
        -- 妙手仓库清单自带的滚动销量窗口。键名无 * 前缀。
        raw_data->>'近7天销量数据' AS sales_7d_raw,
        raw_data->>'近30天销量数据' AS sales_30d_raw,
        raw_data->>'近60天销量数据' AS sales_60d_raw,
        raw_data->>'近90天销量数据' AS sales_90d_raw,
        raw_data,
        header_columns,
        data_hash,
        ingest_timestamp,
        currency_code
    FROM raw_inventory
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
        file_id,
        product_id,
        product_name,
        platform_sku,
        sku_id,
        product_sku,
        warehouse_name,
        warehouse_code,
        CASE
            WHEN available_stock_raw IS NULL THEN NULL
            ELSE NULLIF(
                REGEXP_REPLACE(
                    REPLACE(
                        REPLACE(
                            REPLACE(
                                REPLACE(available_stock_raw, ',', ''),
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
        END AS available_stock,
        CASE
            WHEN on_hand_stock_raw IS NULL THEN NULL
            ELSE NULLIF(
                REGEXP_REPLACE(
                    REPLACE(
                        REPLACE(
                            REPLACE(
                                REPLACE(on_hand_stock_raw, ',', ''),
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
        END AS on_hand_stock,
        CASE
            WHEN reserved_stock_raw IS NULL THEN NULL
            ELSE NULLIF(
                REGEXP_REPLACE(
                    REPLACE(
                        REPLACE(
                            REPLACE(
                                REPLACE(reserved_stock_raw, ',', ''),
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
        END AS reserved_stock,
        CASE
            WHEN in_transit_stock_raw IS NULL THEN NULL
            ELSE NULLIF(
                REGEXP_REPLACE(
                    REPLACE(
                        REPLACE(
                            REPLACE(
                                REPLACE(in_transit_stock_raw, ',', ''),
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
        END AS in_transit_stock,
        CASE
            WHEN stockout_qty_raw IS NULL THEN NULL
            ELSE NULLIF(
                REGEXP_REPLACE(
                    REPLACE(
                        REPLACE(
                            REPLACE(
                                REPLACE(stockout_qty_raw, ',', ''),
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
        END AS stockout_qty,
        CASE
            WHEN reorder_point_raw IS NULL THEN NULL
            ELSE NULLIF(
                REGEXP_REPLACE(
                    REPLACE(
                        REPLACE(
                            REPLACE(
                                REPLACE(reorder_point_raw, ',', ''),
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
        END AS reorder_point,
        CASE
            WHEN safety_stock_raw IS NULL THEN NULL
            ELSE NULLIF(
                REGEXP_REPLACE(
                    REPLACE(
                        REPLACE(
                            REPLACE(
                                REPLACE(safety_stock_raw, ',', ''),
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
        END AS safety_stock,
        CASE
            WHEN unit_cost_raw IS NULL THEN NULL
            ELSE NULLIF(
                REGEXP_REPLACE(
                    REPLACE(
                        REPLACE(
                            REPLACE(
                                REPLACE(unit_cost_raw, ',', ''),
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
        END AS unit_cost,
        CASE
            WHEN inventory_value_raw IS NULL THEN NULL
            ELSE NULLIF(
                REGEXP_REPLACE(
                    REPLACE(
                        REPLACE(
                            REPLACE(
                                REPLACE(inventory_value_raw, ',', ''),
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
        END AS inventory_value,
        -- 行级「最后修改时间」：库存停滞时长的时间基准。
        -- 非标准格式一律落 NULL（不得让整批查询失败）。
        CASE
            WHEN observed_at_raw ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}[ T][0-9]{2}:[0-9]{2}:[0-9]{2}$'
            THEN observed_at_raw::timestamp AT TIME ZONE 'Asia/Shanghai'
            ELSE NULL
        END AS observed_at,
        -- 行级「记录创建时间」：商品在该仓的库存记录首次创建时间。
        CASE
            WHEN created_at_raw ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}[ T][0-9]{2}:[0-9]{2}:[0-9]{2}$'
            THEN created_at_raw::timestamp AT TIME ZONE 'Asia/Shanghai'
            ELSE NULL
        END AS created_at,
        -- 窗口销量：缺失必须落 NULL 而不是 0。
        -- 「销量列不存在」（shopee / tiktok / 该行没有这列）= 不可算；
        -- 「销量列存在且为 0」= 真的零销量。两者必须可区分。
        CASE
            WHEN sales_7d_raw IS NULL THEN NULL
            ELSE NULLIF(REGEXP_REPLACE(REPLACE(sales_7d_raw, ',', ''), '[^0-9.-]', '', 'g'), '')::numeric
        END AS checklist_sales_7d,
        CASE
            WHEN sales_30d_raw IS NULL THEN NULL
            ELSE NULLIF(REGEXP_REPLACE(REPLACE(sales_30d_raw, ',', ''), '[^0-9.-]', '', 'g'), '')::numeric
        END AS checklist_sales_30d,
        CASE
            WHEN sales_60d_raw IS NULL THEN NULL
            ELSE NULLIF(REGEXP_REPLACE(REPLACE(sales_60d_raw, ',', ''), '[^0-9.-]', '', 'g'), '')::numeric
        END AS checklist_sales_60d,
        CASE
            WHEN sales_90d_raw IS NULL THEN NULL
            ELSE NULLIF(REGEXP_REPLACE(REPLACE(sales_90d_raw, ',', ''), '[^0-9.-]', '', 'g'), '')::numeric
        END AS checklist_sales_90d,
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
            ORDER BY ingest_timestamp DESC
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
    sku_id,
    product_sku,
    warehouse_name,
    warehouse_code,
    COALESCE(available_stock, 0) AS available_stock,
    COALESCE(on_hand_stock, 0) AS on_hand_stock,
    COALESCE(reserved_stock, 0) AS reserved_stock,
    COALESCE(in_transit_stock, 0) AS in_transit_stock,
    COALESCE(stockout_qty, 0) AS stockout_qty,
    COALESCE(reorder_point, 0) AS reorder_point,
    COALESCE(safety_stock, 0) AS safety_stock,
    COALESCE(unit_cost, 0) AS unit_cost,
    COALESCE(inventory_value, 0) AS inventory_value,
    raw_data,
    header_columns,
    data_hash,
    ingest_timestamp,
    currency_code,
    file_id,
    -- ↓ 新增列必须追加在末尾（CREATE OR REPLACE VIEW 不允许改变已有列的位置）
    -- 行级「最后修改时间」。没有该列的平台（shopee / tiktok）回落到批次业务日期。
    COALESCE(
        observed_at,
        metric_date::timestamp AT TIME ZONE 'Asia/Shanghai'
    ) AS observed_at,
    -- 行级「记录创建时间」。没有该列的平台落 NULL（表示「取不到」，不是「1970」）。
    created_at,
    -- 窗口销量（妙手仓库清单自带）。缺失落 NULL = 该行不可算。
    checklist_sales_7d,
    checklist_sales_30d,
    checklist_sales_60d,
    checklist_sales_90d
FROM deduplicated
WHERE rn = 1;
