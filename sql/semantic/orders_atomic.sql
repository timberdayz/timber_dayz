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
        -- ── 取数一律走别名表(单一事实源) ──────────────────────────
        --
        -- `semantic.resolve_alias()` 的排序是「平台精确匹配 → 粒度精确匹配
        -- → 置信度 → 来源 → id」, 所以:
        --   * 平台间同业务不同列名(买家实付: shopee「买家支付(RMB)」/
        --     tiktok「买家实付金额(RMB)」)不会抢张;
        --   * 源表里每个金额列都有「原币 + (RMB)」两列, 别名表**只登 (RMB)
        --     变体** ⇒ 裸名(原币列)永远命不中 ⇒ 杜绝混币种。
        --
        -- ⚠ 这里用 `resolve_alias`(逐字)而不是 `resolve_alias_normalized`:
        --   归一化会把「X」与「X(RMB)」压成同一个 key ⇒ 在两个**不同的
        --   业务事实**之间随机取一个(实测两者均值差约 3 倍)。
        semantic.resolve_alias(raw_data, data_domain, 'order_id', platform_code, granularity) AS order_id,
        semantic.resolve_alias(raw_data, data_domain, 'order_status', platform_code, granularity) AS order_status,
        semantic.resolve_alias(raw_data, data_domain, 'profit', platform_code, granularity) AS profit_raw,
        semantic.resolve_alias(raw_data, data_domain, 'purchase_amount', platform_code, granularity) AS purchase_amount_raw,
        semantic.resolve_alias(raw_data, data_domain, 'order_original_amount', platform_code, granularity) AS order_original_amount_raw,
        semantic.resolve_alias(raw_data, data_domain, 'warehouse_operation_fee', platform_code, granularity) AS warehouse_operation_fee_raw,
        semantic.resolve_alias(raw_data, data_domain, 'shipping_fee', platform_code, granularity) AS shipping_fee_raw,
        semantic.resolve_alias(raw_data, data_domain, 'promotion_fee', platform_code, granularity) AS promotion_fee_raw,
        semantic.resolve_alias(raw_data, data_domain, 'platform_commission', platform_code, granularity) AS platform_commission_raw,
        semantic.resolve_alias(raw_data, data_domain, 'platform_deduction_fee', platform_code, granularity) AS platform_deduction_fee_raw,
        semantic.resolve_alias(raw_data, data_domain, 'platform_voucher', platform_code, granularity) AS platform_voucher_raw,
        semantic.resolve_alias(raw_data, data_domain, 'platform_service_fee', platform_code, granularity) AS platform_service_fee_raw,
        -- 联盟/达人佣金(2026-11-08 补登): 付给**达人/联盟**的钱, 与「平台佣金」
        -- 是**两笔钱**(shopee 叫「联盟佣金」/ tiktok 叫「达人佣金」; 用户 2026-11-08 确认)。
        -- ⚠ **不并入** `platform_total_cost_itemized` —— 那 6 项是「平台侧成本」,
        --   联盟佣金是付给达人的, 并进去会与利润口径重复计算。
        semantic.resolve_alias(raw_data, data_domain, 'affiliate_commission', platform_code, granularity) AS affiliate_commission_raw,
        -- 卖家总收入(2026-11-08 补登): 卖家侧商品成交总收入。
        -- 实测(tiktok monthly 5254 行): 与「买家实付金额」行级相等率仅 12.03%
        -- ⇒ 不是同一个事实; 与「产品折后价格」相等率 69.24% ⇒ 成交额口径。
        -- ⚠ **只有 tiktok 有这一列**(shopee 侧对应概念是「预估回款金额 / 已结算金额」,
        --   那是**结算口径**)⇒ shopee 侧恒 NULL(如实反映, 不猜值)。
        semantic.resolve_alias(raw_data, data_domain, 'total_income', platform_code, granularity) AS total_income_raw,
        semantic.resolve_alias(raw_data, data_domain, 'paid_amount', platform_code, granularity) AS paid_amount_raw,
        -- ⚠ 列名是 ``product_quantity``, 但**语义键**是 ``sales_volume``:
        --   订单域的件数列「销售数量」归 ``sales_volume``(契约 + 模板确认 +
        --   字典三处一致), 视图的物理列名是历史遗留 ⇒ 两者不必同名。
        semantic.resolve_alias(raw_data, data_domain, 'sales_volume', platform_code, granularity) AS product_quantity_raw,
        semantic.resolve_alias(raw_data, data_domain, 'buyer_count', platform_code, granularity) AS buyer_count_raw,
        semantic.resolve_alias(raw_data, data_domain, 'product_id', platform_code, granularity) AS product_id,
        semantic.resolve_alias(raw_data, data_domain, 'platform_sku', platform_code, granularity) AS platform_sku,
        semantic.resolve_alias(raw_data, data_domain, 'sku_id', platform_code, granularity) AS sku_id,
        semantic.resolve_alias(raw_data, data_domain, 'product_sku', platform_code, granularity) AS product_sku,
        semantic.resolve_alias(raw_data, data_domain, 'product_name', platform_code, granularity) AS product_name,
        semantic.resolve_alias(raw_data, data_domain, 'order_date', platform_code, granularity) AS order_time_raw,
        -- `sales_amount` 已废止(见 semantic_field_registry.ORDER_RETIRED_FIELDS):
        -- 源表**没有**「销售额/成交金额」这一列, 以前命中的是 tiktok 的
        -- 「总收入」(原币) ⇒ 与 `paid_amount` 抢同一个业务含义且币种还不对。
        -- ⇒ 保留列但恒 NULL(视图不能删列), 不再输出 0 伪值。
        NULL::text AS sales_amount_raw,
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
        source_shop_id,
        store_label_raw,
        source_account,
        source_site,
        -- 站点 → 区域码（大写，与 core.shop_accounts.shop_region 比较）。
        -- 8 项映射与 backend/domains/collection/routers/account_alignment.py 的 `site_map` 对齐
        -- （改一侧必须同时改另一侧；两侧 fallback 的大小写**有意**不同：Python 侧小写只用于
        --  生成建议 id，SQL 侧大写才与 shop_region 比较）。
        CASE lower(NULLIF(TRIM(BOTH FROM COALESCE(source_site, '')), ''))
            WHEN '菲律宾' THEN 'PH'
            WHEN '新加坡' THEN 'SG'
            WHEN '马来' THEN 'MY'
            WHEN '马来西亚' THEN 'MY'
            WHEN '泰国' THEN 'TH'
            WHEN '越南' THEN 'VN'
            WHEN '印尼' THEN 'ID'
            WHEN '巴西' THEN 'BR'
            ELSE UPPER(LEFT(NULLIF(TRIM(BOTH FROM COALESCE(source_site, '')), ''), 2))
        END AS source_region,
        source_platform_shop_id,
        source_shop_account_id,
        -- 候选值集合：就地引用 mapped 的真实输入列（同层不能引用输出别名）
        --
        -- ⚠️ 事实表的「列」shop_id **不是身份列** —— 它装的是采集层写进来的
        -- 原始标识(shopee 平台编号 / tiktok 导出店名 / miaoshou 采集方代号)。
        -- 「xihong」「unknown」「none」「miaoshou_real_001」是**采集方标识**, 不是店铺身份。
        --
        -- 这条排除**不在这里写**：候选池
        -- (``semantic.shop_identity_resolution_candidates``)构建时就已把采集方代号
        -- 剔掉 ⇒ 本处原样带上也不会命中任何账号。
        -- 而该规则**只有一处定义** —— 权威清单
        -- ``modules/core/fact_identity_columns.py::COLLECTION_SOURCE_IDS``、
        -- 登记载体 ``core.collection_source_identifiers`` ——
        -- ⇒ 新增链路自动继承, 不会像以前那样「每条链路各抄一份、漏一条就出事」。
        ARRAY_REMOVE(
            ARRAY[
                LOWER(COALESCE(source_platform_shop_id, '')),
                LOWER(COALESCE(source_shop_account_id, '')),
                LOWER(COALESCE(source_shop_id, '')),
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
                ),
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
                )
            ],
            ''
        ) AS normalized_identity_candidates,
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
            WHEN affiliate_commission_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(affiliate_commission_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(affiliate_commission_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS affiliate_commission,
        CASE
            WHEN total_income_raw IS NULL THEN NULL
            WHEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(total_income_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '') ~ '^-?(?:\d+(?:\.\d*)?|\.\d+)$'
            THEN NULLIF(REGEXP_REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(total_income_raw, ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''), '[^0-9.-]', '', 'g'), '')::numeric
            ELSE NULL
        END AS total_income,
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
            WHEN account_map.candidate_count = 1 THEN account_map.resolved_shop_id
            ELSE 'unknown'
        END AS shop_id,
        CASE
            WHEN COALESCE(d.source_platform_shop_id, d.source_shop_account_id, d.store_label_raw, d.source_shop_id) IS NULL
            THEN 'missing_identity'
            WHEN account_map.candidate_count = 0
            THEN 'unmatched_shop_label'
            WHEN account_map.candidate_count > 1
            THEN 'ambiguous_shop_label'
            WHEN account_map.resolved_shop_account_id IS NULL
            THEN 'unresolved_shop_account'
            WHEN account_map.resolved_shop_account_id IS NOT NULL AND canonical.shop_account_id IS NULL
            THEN 'unresolved_shop_account'
            WHEN account_map.resolved_shop_account_id IS NOT NULL
             AND LOWER(COALESCE(d.platform_code, '')) IN ('shopee')
             AND NULLIF(TRIM(canonical.platform_shop_id), '') IS NULL
            THEN 'missing_required_platform_shop_id'
            ELSE NULL
        END AS identity_warning_code,
        account_map.candidate_count AS identity_candidate_count,
        account_map.candidate_shop_ids::text AS identity_candidates,
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
        -- 2026-11-08 补登的两个标准字段(逐层透传: cleaned → deduplicated → 本层)
        d.affiliate_commission,
        d.total_income,
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
            agg.candidate_count,
            agg.candidate_shop_ids,
            best.resolved_shop_id,
            best.resolved_shop_account_id,
            best.resolution_method,
            best.resolution_priority,
            best.identity_source_value
        FROM (
            -- ① 计数与候选清单：纯聚合，按去重后的店铺算
            SELECT
                count(DISTINCT c.resolved_shop_id)::int AS candidate_count,
                array_agg(DISTINCT c.resolved_shop_id ORDER BY c.resolved_shop_id) AS candidate_shop_ids
            FROM semantic.shop_identity_resolution_candidates_v2_mv c
            WHERE c.platform_code = lower(COALESCE(d.platform_code, ''))
              AND c.identity_value_normalized = ANY (d.normalized_identity_candidates)
              -- 区域感知匹配：层 1 = 区域精确匹配；层 2 = 完整候选集（层 1 为空时的兜底）。
              -- 写成「并集」会凭空制造新的 unknown，这里必须是「层 1 为空才回落完整候选集」。
              AND (
                    (
                        c.identity_shop_region IS NOT NULL
                        AND d.source_region IS NOT NULL
                        AND c.identity_shop_region = d.source_region
                    )
                    OR NOT EXISTS (
                        SELECT 1
                        FROM semantic.shop_identity_resolution_candidates_v2_mv c_exact
                        WHERE c_exact.platform_code = lower(COALESCE(d.platform_code, ''))
                          AND c_exact.identity_value_normalized = ANY (d.normalized_identity_candidates)
                          AND c_exact.identity_shop_region IS NOT NULL
                          AND d.source_region IS NOT NULL
                          AND c_exact.identity_shop_region = d.source_region
                    )
              )
        ) agg
        LEFT JOIN LATERAL (
            -- ② 最优候选：每个店只保留优先级最高的一行
            SELECT DISTINCT ON (c.resolved_shop_id)
                   c.resolved_shop_id,
                   c.resolved_shop_account_id,
                   c.resolution_method,
                   c.resolution_priority,
                   c.identity_source_value
            FROM semantic.shop_identity_resolution_candidates_v2_mv c
            WHERE c.platform_code = lower(COALESCE(d.platform_code, ''))
              AND c.identity_value_normalized = ANY (d.normalized_identity_candidates)
              -- 与 ① 计数子查询**同一段**区域过滤，否则计数与归属会不一致
              AND (
                    (
                        c.identity_shop_region IS NOT NULL
                        AND d.source_region IS NOT NULL
                        AND c.identity_shop_region = d.source_region
                    )
                    OR NOT EXISTS (
                        SELECT 1
                        FROM semantic.shop_identity_resolution_candidates_v2_mv c_exact
                        WHERE c_exact.platform_code = lower(COALESCE(d.platform_code, ''))
                          AND c_exact.identity_value_normalized = ANY (d.normalized_identity_candidates)
                          AND c_exact.identity_shop_region IS NOT NULL
                          AND d.source_region IS NOT NULL
                          AND c_exact.identity_shop_region = d.source_region
                    )
              )
            ORDER BY c.resolved_shop_id, c.resolution_priority, c.resolution_method, c.identity_source_value
        ) best ON TRUE
        ORDER BY best.resolution_priority, best.resolved_shop_id
        LIMIT 1
    ) account_map ON TRUE
    LEFT JOIN core.shop_accounts canonical
      ON LOWER(COALESCE(canonical.platform, '')) = LOWER(COALESCE(d.platform_code, ''))
     AND canonical.shop_account_id = account_map.resolved_shop_account_id
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
    -- ── 出口不再把「取不到数」伪装成 0 ──────────────────────────
    --
    -- ⚠ 以前这里一律 `COALESCE(x, 0)`: 源表缺列 / 解析不出 ⇒ 输出 0,
    -- 0 与「真的是 0」在下游**分不开** ⇒ 缺项被当成"没有成本"。
    -- 实测(2026-11 开发库): 平台成本 6 项里有 3~5 项取不到数,
    -- 以前全部记 0, 成本被系统性低估。
    -- 
    -- ⇒ 现在缺项就是 NULL(「不知道」), 由下游的
    -- `platform_total_cost_known_items` 判断完整度。
    --
    -- `sales_amount` 已废止 ⇒ 恒 NULL(视图不能删列)。
    --   源表没有「销售额/成交金额」这一列, 以前命中的是 tiktok 的「总收入」
    -- (原币) ⇒ 与 `paid_amount` 抢同一个业务含义、币种还不对。
    sales_amount AS sales_amount,
    paid_amount AS paid_amount,
    profit AS profit,
    product_quantity AS product_quantity,
    buyer_count AS buyer_count,
    -- 平台成本 = 已知项之和。缺项按 0 计入 ⇒ **必须**配合
    -- `platform_total_cost_known_items` 一起看(见文件末尾)。
    (
        COALESCE(shipping_fee, 0)
        + COALESCE(promotion_fee, 0)
        + COALESCE(platform_commission, 0)
        + COALESCE(platform_deduction_fee, 0)
        + COALESCE(platform_voucher, 0)
        + COALESCE(platform_service_fee, 0)
    ) AS platform_total_cost_itemized,
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
    currency_code,
    purchase_amount,
    order_original_amount,
    warehouse_operation_fee,
    shipping_fee,
    promotion_fee,
    platform_commission,
    platform_deduction_fee,
    platform_voucher,
    platform_service_fee,
    (
        order_original_amount
        - purchase_amount
        - profit
        - warehouse_operation_fee
    ) AS platform_total_cost_derived,
    identity_warning_code,
    identity_candidate_count,
    identity_candidates,
    -- ── 平台成本「已知项数」(0..6) ──────────────────────────────
    --
    -- `platform_total_cost_itemized` 是**已知项之和** ⇒ 缺项按 0 计入。
    -- 这一列告诉下游「这个数只覆盖了几项成本」, 免得把部分和当成全额。
    -- 
    -- 6 项固定为: 运费 + 推广费 + 平台佣金 + 平台扣费 + 平台代金券 + 平台服务费
    -- (与 `backend/services/semantic_field_registry.py` 的
    -- `ORDER_PLATFORM_COST_COMPONENT_FIELDS` 一一对应)。
    -- 
    -- ⚠ 「仓库操作费」**不在**这 6 项里 —— 它由下游
    -- (`mart.b_cost_shop_month.total_cost_b`)单独相加, 放进来会重复计。
    --
    -- ⚠ 这列是**追加**在末尾的: `CREATE OR REPLACE VIEW` 只能在末尾加列,
    -- 不能删列、不能改列序(见 PostgreSQL 文档)。
    (
        CASE WHEN shipping_fee IS NOT NULL THEN 1 ELSE 0 END
        + CASE WHEN promotion_fee IS NOT NULL THEN 1 ELSE 0 END
        + CASE WHEN platform_commission IS NOT NULL THEN 1 ELSE 0 END
        + CASE WHEN platform_deduction_fee IS NOT NULL THEN 1 ELSE 0 END
        + CASE WHEN platform_voucher IS NOT NULL THEN 1 ELSE 0 END
        + CASE WHEN platform_service_fee IS NOT NULL THEN 1 ELSE 0 END
    ) AS platform_total_cost_known_items,
    -- ── 2026-11-08 补登的两个标准字段 ──────────────────────────────
    -- ⚠ 只能加在**末尾**: `CREATE OR REPLACE VIEW` 不能删列、不能改列序。
    -- 「联盟/达人佣金」: 付给达人的钱(shopee「联盟佣金」/ tiktok「达人佣金」)。
    -- 「卖家总收入」: 卖家侧商品成交总收入(目前只有 tiktok 有 ⇒ shopee 恒 NULL)。
    affiliate_commission,
    total_income
FROM alias_resolved;
