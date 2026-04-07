-- ============================================================================
-- Migration: 001_create_a_class_data_tables
-- Description: 创建A类数据表（用户配置数据）- 销售目标、战役目标、经营成本
-- Purpose: 支持DSS架构中的A类数据管理
-- Created: 2025-11-22
-- ============================================================================

-- ============================================================================
-- 1. 销售目标表（Sales Targets）
-- ============================================================================

CREATE TABLE IF NOT EXISTS sales_targets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shop_id VARCHAR(100) NOT NULL,
    year_month VARCHAR(7) NOT NULL,  -- Format: YYYY-MM
    target_sales_amount DECIMAL(15, 2) NOT NULL CHECK (target_sales_amount >= 0),
    target_order_count INTEGER NOT NULL CHECK (target_order_count >= 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(100),
    
    -- 唯一约束：每个店铺每月只能有一个目标
    CONSTRAINT uq_sales_targets_shop_month UNIQUE (shop_id, year_month)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_sales_targets_shop_id ON sales_targets(shop_id);
CREATE INDEX IF NOT EXISTS idx_sales_targets_year_month ON sales_targets(year_month);
CREATE INDEX IF NOT EXISTS idx_sales_targets_created_at ON sales_targets(created_at);

-- 注释
COMMENT ON TABLE sales_targets IS 'A类数据：销售目标配置表';
COMMENT ON COLUMN sales_targets.shop_id IS '店铺ID（关联dim_shops.shop_id）';
COMMENT ON COLUMN sales_targets.year_month IS '目标月份（YYYY-MM格式）';
COMMENT ON COLUMN sales_targets.target_sales_amount IS '目标销售额（CNY）';
COMMENT ON COLUMN sales_targets.target_order_count IS '目标订单数';

-- ============================================================================
-- 2. 战役目标表（Campaign Targets）
-- ============================================================================

CREATE TABLE IF NOT EXISTS campaign_targets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform_code VARCHAR(50) NOT NULL,
    campaign_name VARCHAR(255) NOT NULL,
    campaign_type VARCHAR(100),  -- 'double_11', 'new_year', 'flash_sale', etc.
    start_date DATE NOT NULL,
    end_date DATE NOT NULL CHECK (end_date >= start_date),
    target_gmv DECIMAL(15, 2) NOT NULL CHECK (target_gmv >= 0),
    target_roi DECIMAL(10, 2) CHECK (target_roi >= 0),  -- ROI目标（例如3.5表示3.5倍回报）
    budget_amount DECIMAL(15, 2) CHECK (budget_amount >= 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(100),
    
    -- 唯一约束：同一平台同一时间段不能有重名战役
    CONSTRAINT uq_campaign_targets_platform_name_dates UNIQUE (platform_code, campaign_name, start_date, end_date)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_campaign_targets_platform ON campaign_targets(platform_code);
CREATE INDEX IF NOT EXISTS idx_campaign_targets_dates ON campaign_targets(start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_campaign_targets_type ON campaign_targets(campaign_type);
CREATE INDEX IF NOT EXISTS idx_campaign_targets_created_at ON campaign_targets(created_at);

-- 注释
COMMENT ON TABLE campaign_targets IS 'A类数据：战役目标配置表';
COMMENT ON COLUMN campaign_targets.platform_code IS '平台代码（如shopee, tiktok）';
COMMENT ON COLUMN campaign_targets.campaign_name IS '战役名称（如"双十一大促"）';
COMMENT ON COLUMN campaign_targets.target_gmv IS '目标GMV（CNY）';
COMMENT ON COLUMN campaign_targets.target_roi IS '目标ROI（如3.5表示投入产出比1:3.5）';

-- ============================================================================
-- 3. 经营成本表（Operating Costs）
-- ============================================================================

CREATE TABLE IF NOT EXISTS operating_costs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shop_id VARCHAR(100) NOT NULL,
    year_month VARCHAR(7) NOT NULL,  -- Format: YYYY-MM
    rent DECIMAL(15, 2) DEFAULT 0 CHECK (rent >= 0),
    salary DECIMAL(15, 2) DEFAULT 0 CHECK (salary >= 0),
    marketing DECIMAL(15, 2) DEFAULT 0 CHECK (marketing >= 0),
    logistics DECIMAL(15, 2) DEFAULT 0 CHECK (logistics >= 0),
    utilities DECIMAL(15, 2) DEFAULT 0 CHECK (utilities >= 0),
    other DECIMAL(15, 2) DEFAULT 0 CHECK (other >= 0),
    total DECIMAL(15, 2) GENERATED ALWAYS AS (
        COALESCE(rent, 0) + 
        COALESCE(salary, 0) + 
        COALESCE(marketing, 0) + 
        COALESCE(logistics, 0) + 
        COALESCE(utilities, 0) + 
        COALESCE(other, 0)
    ) STORED,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(100),
    
    -- 唯一约束：每个店铺每月只能有一条成本记录
    CONSTRAINT uq_operating_costs_shop_month UNIQUE (shop_id, year_month)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_operating_costs_shop_id ON operating_costs(shop_id);
CREATE INDEX IF NOT EXISTS idx_operating_costs_year_month ON operating_costs(year_month);
CREATE INDEX IF NOT EXISTS idx_operating_costs_created_at ON operating_costs(created_at);

-- 注释
COMMENT ON TABLE operating_costs IS 'A类数据：经营成本配置表';
COMMENT ON COLUMN operating_costs.shop_id IS '店铺ID（关联dim_shops.shop_id）';
COMMENT ON COLUMN operating_costs.year_month IS '成本月份（YYYY-MM格式）';
COMMENT ON COLUMN operating_costs.rent IS '租金成本（CNY）';
COMMENT ON COLUMN operating_costs.salary IS '工资成本（CNY）';
COMMENT ON COLUMN operating_costs.marketing IS '营销成本（CNY）';
COMMENT ON COLUMN operating_costs.logistics IS '物流成本（CNY）';
COMMENT ON COLUMN operating_costs.utilities IS '水电等公用事业成本（CNY）';
COMMENT ON COLUMN operating_costs.other IS '其他成本（CNY）';
COMMENT ON COLUMN operating_costs.total IS '总成本（自动计算）';

-- ============================================================================
-- 4. 外键约束（如果dim_shops表存在）
-- ============================================================================

-- 注意：这些外键约束依赖dim_shops表的存在
-- 如果dim_shops表不存在，这些语句会失败，需要手动执行

DO $$
BEGIN
    -- 为sales_targets添加外键
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'dim_shops') THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints 
            WHERE constraint_name = 'fk_sales_targets_shop'
        ) THEN
            ALTER TABLE sales_targets 
            ADD CONSTRAINT fk_sales_targets_shop 
            FOREIGN KEY (shop_id) REFERENCES dim_shops(shop_id) ON DELETE CASCADE;
        END IF;
    END IF;
    
    -- 为operating_costs添加外键
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'dim_shops') THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints 
            WHERE constraint_name = 'fk_operating_costs_shop'
        ) THEN
            ALTER TABLE operating_costs 
            ADD CONSTRAINT fk_operating_costs_shop 
            FOREIGN KEY (shop_id) REFERENCES dim_shops(shop_id) ON DELETE CASCADE;
        END IF;
    END IF;
END $$;

-- ============================================================================
-- 5. 触发器：自动更新updated_at字段
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 为每个表创建触发器
DROP TRIGGER IF EXISTS update_sales_targets_updated_at ON sales_targets;
CREATE TRIGGER update_sales_targets_updated_at 
BEFORE UPDATE ON sales_targets 
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_campaign_targets_updated_at ON campaign_targets;
CREATE TRIGGER update_campaign_targets_updated_at 
BEFORE UPDATE ON campaign_targets 
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_operating_costs_updated_at ON operating_costs;
CREATE TRIGGER update_operating_costs_updated_at 
BEFORE UPDATE ON operating_costs 
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 6. 示例数据（可选）
-- ============================================================================

-- 插入示例销售目标
-- INSERT INTO sales_targets (shop_id, year_month, target_sales_amount, target_order_count, created_by)
-- VALUES 
--     ('shop_001', '2025-01', 1000000.00, 5000, 'admin'),
--     ('shop_001', '2025-02', 1200000.00, 6000, 'admin'),
--     ('shop_002', '2025-01', 500000.00, 2500, 'admin');

-- 插入示例战役目标
-- INSERT INTO campaign_targets (platform_code, campaign_name, campaign_type, start_date, end_date, target_gmv, target_roi, budget_amount, created_by)
-- VALUES 
--     ('shopee', '双十一大促', 'double_11', '2025-11-01', '2025-11-11', 5000000.00, 3.5, 1400000.00, 'admin'),
--     ('tiktok', '春节狂欢', 'new_year', '2025-01-20', '2025-02-05', 3000000.00, 4.0, 750000.00, 'admin');

-- 插入示例经营成本
-- INSERT INTO operating_costs (shop_id, year_month, rent, salary, marketing, logistics, other, created_by)
-- VALUES 
--     ('shop_001', '2025-01', 50000.00, 200000.00, 100000.00, 80000.00, 30000.00, 'admin'),
--     ('shop_001', '2025-02', 50000.00, 210000.00, 120000.00, 85000.00, 35000.00, 'admin'),
--     ('shop_002', '2025-01', 30000.00, 100000.00, 50000.00, 40000.00, 15000.00, 'admin');

-- ============================================================================
-- 验证
-- ============================================================================

-- 查看创建的表
-- SELECT table_name, table_type 
-- FROM information_schema.tables 
-- WHERE table_name IN ('sales_targets', 'campaign_targets', 'operating_costs');

-- 查看表结构
-- \d sales_targets
-- \d campaign_targets
-- \d operating_costs

