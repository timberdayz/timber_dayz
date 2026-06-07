CREATE SCHEMA IF NOT EXISTS semantic;

CREATE TABLE IF NOT EXISTS semantic.semantic_field_aliases (
    id BIGSERIAL PRIMARY KEY,
    data_domain TEXT NOT NULL,
    standard_field TEXT NOT NULL,
    raw_alias TEXT NOT NULL,
    platform_code TEXT NULL,
    granularity TEXT NULL,
    source TEXT NOT NULL DEFAULT 'builtin',
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 1.000,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_semantic_field_aliases_source
        CHECK (source IN ('builtin', 'template_confirmed', 'manual')),
    CONSTRAINT ck_semantic_field_aliases_status
        CHECK (status IN ('active', 'disabled')),
    CONSTRAINT uq_semantic_field_aliases_identity
        UNIQUE (data_domain, standard_field, raw_alias, platform_code, granularity)
);

CREATE INDEX IF NOT EXISTS idx_semantic_field_aliases_lookup
    ON semantic.semantic_field_aliases (data_domain, standard_field, status);

CREATE UNIQUE INDEX IF NOT EXISTS uq_semantic_field_aliases_identity_norm
    ON semantic.semantic_field_aliases (
        data_domain,
        standard_field,
        raw_alias,
        COALESCE(platform_code, ''),
        COALESCE(granularity, '')
    );

CREATE OR REPLACE FUNCTION semantic.resolve_alias(
    raw_data JSONB,
    data_domain TEXT,
    standard_field TEXT,
    platform_code TEXT DEFAULT NULL,
    granularity TEXT DEFAULT NULL
) RETURNS TEXT
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    resolved_value TEXT;
BEGIN
    SELECT NULLIF(raw_data ->> alias.raw_alias, '')
    INTO resolved_value
    FROM semantic.semantic_field_aliases alias
    WHERE alias.status = 'active'
      AND alias.data_domain = resolve_alias.data_domain
      AND alias.standard_field = resolve_alias.standard_field
      AND (alias.platform_code IS NULL OR alias.platform_code = resolve_alias.platform_code)
      AND (alias.granularity IS NULL OR alias.granularity = resolve_alias.granularity)
      AND NULLIF(raw_data ->> alias.raw_alias, '') IS NOT NULL
    ORDER BY
      CASE WHEN alias.platform_code = resolve_alias.platform_code THEN 0 ELSE 1 END,
      CASE WHEN alias.granularity = resolve_alias.granularity THEN 0 ELSE 1 END,
      alias.confidence DESC,
      CASE alias.source
        WHEN 'manual' THEN 0
        WHEN 'template_confirmed' THEN 1
        ELSE 2
      END,
      alias.id
    LIMIT 1;

    RETURN resolved_value;
END;
$$;

INSERT INTO semantic.semantic_field_aliases
    (data_domain, standard_field, raw_alias, source, confidence, status)
VALUES
    ('products', 'product_id', '商品ID', 'builtin', 1.000, 'active'),
    ('products', 'product_id', '产品ID', 'builtin', 1.000, 'active'),
    ('products', 'product_id', '商品 ID', 'builtin', 1.000, 'active'),
    ('products', 'product_id', 'product_id', 'builtin', 1.000, 'active'),
    ('products', 'product_id', 'Product ID', 'builtin', 1.000, 'active'),
    ('products', 'product_id', 'item_id', 'builtin', 1.000, 'active'),
    ('products', 'product_name', '商品名称', 'builtin', 1.000, 'active'),
    ('products', 'product_name', '产品名称', 'builtin', 1.000, 'active'),
    ('products', 'product_name', '商品标题', 'builtin', 1.000, 'active'),
    ('products', 'product_name', '商品名', 'builtin', 1.000, 'active'),
    ('products', 'product_name', 'product_name', 'builtin', 1.000, 'active'),
    ('products', 'product_name', 'Product Name', 'builtin', 1.000, 'active'),
    ('products', 'product_name', 'title', 'builtin', 1.000, 'active'),
    ('products', 'item_status', '商品状态', 'builtin', 1.000, 'active'),
    ('products', 'item_status', '状态', 'builtin', 1.000, 'active'),
    ('products', 'item_status', '发品状态', 'builtin', 1.000, 'active'),
    ('products', 'item_status', 'item_status', 'builtin', 1.000, 'active'),
    ('products', 'item_status', 'Item Status', 'builtin', 1.000, 'active'),
    ('products', 'item_status', 'status', 'builtin', 1.000, 'active'),
    ('products', 'order_count', '订单数', 'builtin', 1.000, 'active'),
    ('products', 'order_count', '订单数量', 'builtin', 1.000, 'active'),
    ('products', 'order_count', 'order_count', 'builtin', 1.000, 'active'),
    ('products', 'order_count', 'Order Count', 'builtin', 1.000, 'active'),
    ('products', 'order_count', 'orders', 'builtin', 1.000, 'active'),
    ('products', 'sales_amount', '销售额', 'builtin', 1.000, 'active'),
    ('products', 'sales_amount', '销售金额', 'builtin', 1.000, 'active'),
    ('products', 'sales_amount', 'GMV', 'builtin', 1.000, 'active'),
    ('products', 'sales_amount', 'sales_amount', 'builtin', 1.000, 'active'),
    ('products', 'sales_amount', 'Sales Amount', 'builtin', 1.000, 'active'),
    ('products', 'sales_amount', 'revenue', 'builtin', 1.000, 'active'),
    ('products', 'sales_volume', '件数', 'builtin', 1.000, 'active'),
    ('products', 'sales_volume', '销量', 'builtin', 1.000, 'active'),
    ('products', 'sales_volume', '销售数量', 'builtin', 1.000, 'active'),
    ('products', 'sales_volume', '商品成交件数', 'builtin', 1.000, 'active'),
    ('products', 'sales_volume', 'sales_volume', 'builtin', 1.000, 'active'),
    ('products', 'sales_volume', 'Sales Volume', 'builtin', 1.000, 'active'),
    ('products', 'sales_volume', 'qty', 'builtin', 1.000, 'active'),
    ('products', 'impressions', '曝光次数', 'builtin', 1.000, 'active'),
    ('products', 'impressions', 'impressions', 'builtin', 1.000, 'active'),
    ('products', 'impressions', 'Impressions', 'builtin', 1.000, 'active'),
    ('products', 'clicks', '点击次数', 'builtin', 1.000, 'active'),
    ('products', 'clicks', 'clicks', 'builtin', 1.000, 'active'),
    ('products', 'clicks', 'Clicks', 'builtin', 1.000, 'active'),
    ('products', 'conversion_rate', '转化率', 'builtin', 1.000, 'active'),
    ('products', 'conversion_rate', 'conversion_rate', 'builtin', 1.000, 'active'),
    ('products', 'conversion_rate', 'Conversion Rate', 'builtin', 1.000, 'active'),
    ('products', 'conversion_rate', 'CVR', 'builtin', 1.000, 'active')
ON CONFLICT (
    data_domain,
    standard_field,
    raw_alias,
    COALESCE(platform_code, ''),
    COALESCE(granularity, '')
)
DO UPDATE SET updated_at = NOW(), status = EXCLUDED.status;
