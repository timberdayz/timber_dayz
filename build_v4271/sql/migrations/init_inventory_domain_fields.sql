-- ============================================================
-- 初始化inventory数据域标准字段
-- 时间: 2025-11-05
-- 版本: v4.10.0
-- 说明: 为inventory域添加标准字段定义到field_mapping_dictionary表
-- ============================================================

-- Step 1: 添加inventory域的核心字段
INSERT INTO field_mapping_dictionary 
    (field_code, cn_name, en_name, data_domain, field_group, is_required, data_type, description, synonyms, active, created_by, created_at)
VALUES
    -- 核心标识字段（v4.10.0更新：platform_code和shop_id改为可选，库存数据是仓库级别的）
    ('platform_code', '平台代码', 'Platform Code', 'inventory', 'dimension', false, 'string',
     '数据来源平台代码（inventory域允许为空，其他域必填）',
     '["平台代码", "平台", "platform_code", "platform", "平台标识"]'::jsonb,
     true, 'system', NOW()),
    
    ('shop_id', '店铺ID', 'Shop ID', 'inventory', 'dimension', false, 'string',
     '店铺唯一标识符（inventory域允许为空，其他域必填）',
     '["店铺ID", "店铺", "shop_id", "shop", "店铺编号"]'::jsonb,
     true, 'system', NOW()),
    
    ('platform_sku', '产品SKU', 'Platform SKU', 'inventory', 'dimension', true, 'string',
     '平台产品SKU（唯一标识）',
     '["产品SKU", "SKU", "platform_sku", "product_sku", "商品SKU", "货号"]'::jsonb,
     true, 'system', NOW()),
    
    -- 库存数量字段
    ('total_stock', '库存总量', 'Total Stock', 'inventory', 'metric', false, 'integer',
     '所有持有的库存数量（总量）',
     '["库存总量", "总库存", "total_stock", "total_inventory", "库存总数"]'::jsonb,
     true, 'system', NOW()),
    
    ('available_stock', '可用库存', 'Available Stock', 'inventory', 'metric', false, 'integer',
     '可售卖的库存数量',
     '["可用库存", "可售库存", "可销售库存", "available_stock", "sellable_stock", "可卖库存"]'::jsonb,
     true, 'system', NOW()),
    
    ('reserved_stock', '预占库存', 'Reserved Stock', 'inventory', 'metric', false, 'integer',
     '已拍但是未付款的库存数量',
     '["预占库存", "预留库存", "占用库存", "reserved_stock", "allocated_stock", "锁定库存"]'::jsonb,
     true, 'system', NOW()),
    
    ('in_transit_stock', '在途库存', 'In-Transit Stock', 'inventory', 'metric', false, 'integer',
     '正在从生产地发往仓库的数量（不可售卖）',
     '["在途库存", "运输中库存", "在运库存", "in_transit_stock", "in_transit", "在途"]'::jsonb,
     true, 'system', NOW()),
    
    ('stock', '库存', 'Stock', 'inventory', 'metric', false, 'integer',
     '库存数量（兼容字段，优先使用total_stock）',
     '["库存", "库存数量", "stock", "inventory", "库存数"]'::jsonb,
     true, 'system', NOW()),
    
    -- 仓库信息字段
    ('warehouse', '仓库', 'Warehouse', 'inventory', 'dimension', false, 'string',
     '货物存放仓库位置或代码',
     '["仓库", "仓库代码", "warehouse", "warehouse_code", "仓库位置", "库位"]'::jsonb,
     true, 'system', NOW()),
    
    -- 时间字段
    ('metric_date', '指标日期', 'Metric Date', 'inventory', 'datetime', true, 'date',
     '库存快照日期',
     '["指标日期", "统计日期", "日期", "metric_date", "date", "快照日期", "库存日期"]'::jsonb,
     true, 'system', NOW()),
    
    ('granularity', '粒度', 'Granularity', 'inventory', 'dimension', false, 'string',
     '数据粒度（inventory域固定为snapshot）',
     '["粒度", "granularity", "时间粒度"]'::jsonb,
     true, 'system', NOW())
ON CONFLICT (field_code) DO UPDATE SET
    cn_name = EXCLUDED.cn_name,
    data_domain = EXCLUDED.data_domain,  -- 更新data_domain（如果字段已存在但data_domain不同）
    synonyms = EXCLUDED.synonyms,
    updated_at = NOW();

-- Step 2: 更新现有库存字段的data_domain（如果它们之前属于products域）
UPDATE field_mapping_dictionary
SET data_domain = 'inventory',
    updated_at = NOW()
WHERE field_code IN ('total_stock', 'available_stock', 'reserved_stock', 'in_transit_stock', 'warehouse')
  AND data_domain = 'products';

-- 完成提示
SELECT 'inventory域标准字段初始化成功！' as status;

