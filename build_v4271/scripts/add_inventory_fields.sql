-- ============================================================
-- 添加4个细分库存字段到fact_product_metrics表
-- 时间: 2025-11-05
-- 说明: 支持妙手ERP产品数据域的细分库存映射
-- ============================================================

-- Step 1: 添加4个库存字段到表
ALTER TABLE fact_product_metrics 
ADD COLUMN IF NOT EXISTS total_stock INTEGER NULL;

ALTER TABLE fact_product_metrics 
ADD COLUMN IF NOT EXISTS available_stock INTEGER NULL;

ALTER TABLE fact_product_metrics 
ADD COLUMN IF NOT EXISTS reserved_stock INTEGER NULL;

ALTER TABLE fact_product_metrics 
ADD COLUMN IF NOT EXISTS in_transit_stock INTEGER NULL;

-- 添加列注释
COMMENT ON COLUMN fact_product_metrics.total_stock IS '库存总量：所有持有的库存数量';
COMMENT ON COLUMN fact_product_metrics.available_stock IS '可用库存：可售卖的库存数量';
COMMENT ON COLUMN fact_product_metrics.reserved_stock IS '预占库存：已拍但未付款的库存数量';
COMMENT ON COLUMN fact_product_metrics.in_transit_stock IS '在途库存：正在从生产地发往仓库的数量（不可售卖）';

-- Step 2: 添加字段映射字典条目
INSERT INTO field_mapping_dictionary 
    (field_code, cn_name, en_name, data_domain, field_group, is_required, data_type, description, synonyms, active, created_by, created_at)
VALUES
    ('total_stock', '库存总量', 'Total Stock', 'products', 'metric', false, 'integer', 
     '所有持有的库存数量', 
     '["库存总量", "总库存", "全部库存", "total_stock", "total_inventory"]'::jsonb,
     true, 'system', NOW())
ON CONFLICT (field_code) DO UPDATE SET
    cn_name = EXCLUDED.cn_name,
    synonyms = EXCLUDED.synonyms,
    updated_at = NOW();

INSERT INTO field_mapping_dictionary 
    (field_code, cn_name, en_name, data_domain, field_group, is_required, data_type, description, synonyms, active, created_by, created_at)
VALUES
    ('available_stock', '可用库存', 'Available Stock', 'products', 'metric', false, 'integer',
     '可售卖的库存数量',
     '["可用库存", "可售库存", "可销售库存", "available_stock", "sellable_stock"]'::jsonb,
     true, 'system', NOW())
ON CONFLICT (field_code) DO UPDATE SET
    cn_name = EXCLUDED.cn_name,
    synonyms = EXCLUDED.synonyms,
    updated_at = NOW();

INSERT INTO field_mapping_dictionary 
    (field_code, cn_name, en_name, data_domain, field_group, is_required, data_type, description, synonyms, active, created_by, created_at)
VALUES
    ('reserved_stock', '预占库存', 'Reserved Stock', 'products', 'metric', false, 'integer',
     '已拍但是未付款的库存数量',
     '["预占库存", "预留库存", "占用库存", "reserved_stock", "allocated_stock"]'::jsonb,
     true, 'system', NOW())
ON CONFLICT (field_code) DO UPDATE SET
    cn_name = EXCLUDED.cn_name,
    synonyms = EXCLUDED.synonyms,
    updated_at = NOW();

INSERT INTO field_mapping_dictionary 
    (field_code, cn_name, en_name, data_domain, field_group, is_required, data_type, description, synonyms, active, created_by, created_at)
VALUES
    ('in_transit_stock', '在途库存', 'In-Transit Stock', 'products', 'metric', false, 'integer',
     '正在从生产地发往仓库的数量（不可售卖）',
     '["在途库存", "运输中库存", "在运库存", "in_transit_stock", "in_transit"]'::jsonb,
     true, 'system', NOW())
ON CONFLICT (field_code) DO UPDATE SET
    cn_name = EXCLUDED.cn_name,
    synonyms = EXCLUDED.synonyms,
    updated_at = NOW();

-- Step 3: 更新price字段的同义词（添加"单价"相关）
UPDATE field_mapping_dictionary
SET synonyms = jsonb_set(
    COALESCE(synonyms, '[]'::jsonb),
    '{999}',
    '"单价"'::jsonb
)
WHERE field_code = 'price'
  AND NOT (synonyms @> '["单价"]'::jsonb);

UPDATE field_mapping_dictionary
SET synonyms = jsonb_set(
    COALESCE(synonyms, '[]'::jsonb),
    '{999}',
    '"单价（元）"'::jsonb
)
WHERE field_code = 'price'
  AND NOT (synonyms @> '["单价（元）"]'::jsonb);

UPDATE field_mapping_dictionary
SET synonyms = jsonb_set(
    COALESCE(synonyms, '[]'::jsonb),
    '{999}',
    '"*单价（元）"'::jsonb
)
WHERE field_code = 'price'
  AND NOT (synonyms @> '["*单价（元）"]'::jsonb);

UPDATE field_mapping_dictionary
SET synonyms = jsonb_set(
    COALESCE(synonyms, '[]'::jsonb),
    '{999}',
    '"dan_jia"'::jsonb
)
WHERE field_code = 'price'
  AND NOT (synonyms @> '["dan_jia"]'::jsonb);

UPDATE field_mapping_dictionary
SET synonyms = jsonb_set(
    COALESCE(synonyms, '[]'::jsonb),
    '{999}',
    '"unit_price"'::jsonb
)
WHERE field_code = 'price'
  AND NOT (synonyms @> '["unit_price"]'::jsonb);

-- Step 4: 验证结果
SELECT '=== 验证: fact_product_metrics表的库存字段 ===' as info;
SELECT column_name, data_type, col_description('fact_product_metrics'::regclass, ordinal_position) as description
FROM information_schema.columns
WHERE table_name = 'fact_product_metrics'
  AND column_name LIKE '%stock%'
ORDER BY ordinal_position;

SELECT '=== 验证: 字段映射字典的库存字段 ===' as info;
SELECT field_code, cn_name, en_name, synonyms
FROM field_mapping_dictionary
WHERE field_code IN ('total_stock', 'available_stock', 'reserved_stock', 'in_transit_stock', 'stock')
ORDER BY field_code;

SELECT '=== 验证: price字段的同义词 ===' as info;
SELECT field_code, cn_name, synonyms
FROM field_mapping_dictionary
WHERE field_code = 'price';

