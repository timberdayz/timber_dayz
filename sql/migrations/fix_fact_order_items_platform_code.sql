-- 修复fact_order_items表缺少platform_code字段的问题
-- 创建日期: 2025-01-31
-- 问题: fact_order_items表缺少platform_code字段，导致数据入库失败

-- 步骤1: 检查字段是否存在
DO $$
BEGIN
    -- 检查platform_code字段是否存在
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'fact_order_items' 
        AND column_name = 'platform_code'
    ) THEN
        -- 步骤2: 添加platform_code字段（允许NULL，先添加）
        ALTER TABLE fact_order_items 
        ADD COLUMN platform_code VARCHAR(32);
        
        -- 步骤3: 从fact_orders表更新platform_code（如果order_id匹配）
        UPDATE fact_order_items foi
        SET platform_code = fo.platform_code
        FROM fact_orders fo
        WHERE foi.order_id = fo.order_id
        AND foi.platform_code IS NULL;
        
        -- 步骤4: 设置默认值（对于无法匹配的记录）
        UPDATE fact_order_items
        SET platform_code = 'unknown'
        WHERE platform_code IS NULL;
        
        -- 步骤5: 设置为NOT NULL
        ALTER TABLE fact_order_items 
        ALTER COLUMN platform_code SET NOT NULL;
        
        -- 步骤6: 创建索引（如果不存在）
        IF NOT EXISTS (
            SELECT 1 
            FROM pg_indexes 
            WHERE tablename = 'fact_order_items' 
            AND indexname = 'ix_fact_items_plat_shop_order'
        ) THEN
            CREATE INDEX ix_fact_items_plat_shop_order 
            ON fact_order_items (platform_code, shop_id, order_id);
        END IF;
        
        -- 步骤7: 更新唯一约束（如果存在）
        -- 注意：PostgreSQL的唯一约束可能需要先删除再重建
        -- 这里假设唯一约束是(platform_code, shop_id, order_id, platform_sku)
        -- 如果约束不存在，需要手动创建
        
        RAISE NOTICE '已成功添加platform_code字段到fact_order_items表';
    ELSE
        RAISE NOTICE 'platform_code字段已存在，无需修改';
    END IF;
END $$;

-- 验证：检查字段是否添加成功
SELECT 
    column_name, 
    data_type, 
    is_nullable,
    column_default
FROM information_schema.columns 
WHERE table_name = 'fact_order_items' 
AND column_name = 'platform_code';

