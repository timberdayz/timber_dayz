-- 查询products数据域的库存相关字段
SELECT 
    field_code,
    cn_name,
    en_name,
    data_type,
    is_required,
    description
FROM field_mapping_dictionary
WHERE data_domain = 'products'
    AND (
        field_code LIKE '%stock%' 
        OR field_code LIKE '%inventory%'
        OR cn_name LIKE '%库存%'
    )
ORDER BY field_code;

-- 检查是否有"在手库存"
SELECT 'Check for zai_shou_ku_cun field:' as info;
SELECT field_code, cn_name, en_name
FROM field_mapping_dictionary
WHERE cn_name LIKE '%在手%'
    OR field_code LIKE '%zai_shou%'
    OR en_name LIKE '%on_hand%';

-- 查询stock字段的定义
SELECT 'Current stock field definition:' as info;
SELECT 
    field_code,
    cn_name,
    en_name,
    data_type,
    description,
    synonyms
FROM field_mapping_dictionary
WHERE field_code = 'stock';

-- 检查FactProductMetric表的实际列
SELECT 'Stock-related columns in fact_product_metrics:' as info;
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'fact_product_metrics'
    AND column_name LIKE '%stock%'
ORDER BY ordinal_position;

