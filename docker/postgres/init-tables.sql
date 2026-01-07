-- ===================================================
-- 西虹ERP系统 - 数据库表初始化SQL脚本
-- ===================================================
-- ⚠️ 警告：此文件已废弃，不应再使用！
-- 
-- 所有表定义现在统一在 modules/core/db/schema.py（SSOT - Single Source of Truth）
-- 请使用以下方式创建表：
-- 1. Python方式（推荐）：python backend/apply_migrations.py
-- 2. 代码方式：from backend.models.database import init_db; init_db()
-- 
-- 功能：
-- 1. 创建所有核心表
-- 2. 插入示例数据
-- 3. 创建性能优化索引
-- 4. 支持幂等性（可重复运行）
-- ===================================================

-- 创建账号表
CREATE TABLE IF NOT EXISTS accounts (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(50) NOT NULL,
    username VARCHAR(100) NOT NULL,
    password VARCHAR(500),
    login_url VARCHAR(500),
    status VARCHAR(20) DEFAULT 'offline',
    health_score FLOAT DEFAULT 0.0,
    notes VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建数据记录表
CREATE TABLE IF NOT EXISTS data_records (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(50) NOT NULL,
    data_type VARCHAR(100) NOT NULL,
    record_count INTEGER DEFAULT 0,
    quality_score FLOAT DEFAULT 0.0,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建平台维度表
CREATE TABLE IF NOT EXISTS dim_platform (
    platform_code VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100)
);

-- 创建店铺维度表
CREATE TABLE IF NOT EXISTS dim_shop (
    shop_id VARCHAR(100) PRIMARY KEY,
    platform_code VARCHAR(50) NOT NULL,
    account VARCHAR(100),
    shop_name VARCHAR(200),
    country VARCHAR(10)
);

-- 创建产品维度表
CREATE TABLE IF NOT EXISTS dim_product (
    product_surrogate_id SERIAL PRIMARY KEY,
    platform_code VARCHAR(50) NOT NULL,
    platform_sku VARCHAR(200) NOT NULL,
    product_name VARCHAR(500),
    category VARCHAR(200),
    brand VARCHAR(200),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建销售订单事实表
CREATE TABLE IF NOT EXISTS fact_sales_orders (
    id SERIAL PRIMARY KEY,
    platform_code VARCHAR(50) NOT NULL,
    shop_id VARCHAR(100) NOT NULL,
    order_id VARCHAR(200) NOT NULL,
    order_date TIMESTAMP NOT NULL,
    total_amount FLOAT DEFAULT 0.0,
    currency VARCHAR(10) DEFAULT 'USD',
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建产品指标事实表
CREATE TABLE IF NOT EXISTS fact_product_metrics (
    id SERIAL PRIMARY KEY,
    platform_code VARCHAR(50) NOT NULL,
    shop_id VARCHAR(100) NOT NULL,
    product_surrogate_id INTEGER NOT NULL,
    metric_date TIMESTAMP NOT NULL,
    views INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    orders INTEGER DEFAULT 0,
    revenue FLOAT DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建字段映射表
CREATE TABLE IF NOT EXISTS field_mappings (
    id SERIAL PRIMARY KEY,
    file_name VARCHAR(200) NOT NULL,
    platform VARCHAR(50) NOT NULL,
    excel_field VARCHAR(100) NOT NULL,
    standard_field VARCHAR(100) NOT NULL,
    confidence_score FLOAT DEFAULT 0.0,
    mapping_method VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建映射会话表
CREATE TABLE IF NOT EXISTS mapping_sessions (
    id SERIAL PRIMARY KEY,
    session_name VARCHAR(200) NOT NULL,
    platform VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建数据文件表
CREATE TABLE IF NOT EXISTS data_files (
    id SERIAL PRIMARY KEY,
    file_name VARCHAR(200) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    platform VARCHAR(50) NOT NULL,
    file_type VARCHAR(50),
    file_size BIGINT,
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建采集任务表
CREATE TABLE IF NOT EXISTS collection_tasks (
    id SERIAL PRIMARY KEY,
    task_name VARCHAR(200) NOT NULL,
    platform VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建原始数据表
CREATE TABLE IF NOT EXISTS raw_ingestions (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(50) NOT NULL,
    data_type VARCHAR(100) NOT NULL,
    raw_data JSONB,
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建数据隔离表
CREATE TABLE IF NOT EXISTS data_quarantine (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(50) NOT NULL,
    data_type VARCHAR(100) NOT NULL,
    quarantine_reason VARCHAR(500),
    raw_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建暂存订单表
CREATE TABLE IF NOT EXISTS staging_orders (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(50) NOT NULL,
    shop_id VARCHAR(100) NOT NULL,
    order_id VARCHAR(200) NOT NULL,
    order_data JSONB,
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建暂存产品指标表
CREATE TABLE IF NOT EXISTS staging_product_metrics (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(50) NOT NULL,
    shop_id VARCHAR(100) NOT NULL,
    product_sku VARCHAR(200) NOT NULL,
    metric_data JSONB,
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ⚠️ 警告：此文件已废弃，不应再使用！
-- 所有表定义现在统一在 modules/core/db/schema.py（SSOT - Single Source of Truth）
-- 请使用 backend/apply_migrations.py 或 backend/models/database.py 中的 init_db() 来创建表
-- 
-- 旧版本的 catalog_files 表定义已删除（2026-01-02）
-- 正确的表定义请参考：modules/core/db/schema.py 中的 CatalogFile 类
-- 
-- 如果数据库中的 catalog_files 表缺少字段，请运行：
-- python backend/apply_migrations.py
-- 该脚本会自动检查并添加缺失的列

-- 插入平台维度数据
INSERT INTO dim_platform (platform_code, name) VALUES 
    ('SHOPEE', 'Shopee'),
    ('TIKTOK', 'TikTok Shop'),
    ('AMAZON', 'Amazon'),
    ('MIAOSHOU', '妙手ERP')
ON CONFLICT (platform_code) DO NOTHING;

-- 插入示例账号数据
INSERT INTO accounts (platform, username, password, login_url, status, health_score, notes) VALUES 
    ('SHOPEE', 'shopee_main', 'encrypted_password_1', 'https://shopee.com/login', 'online', 95.0, '主要Shopee账号'),
    ('TIKTOK', 'tiktok_shop_1', 'encrypted_password_2', 'https://seller.tiktok.com/login', 'online', 88.0, 'TikTok小店账号'),
    ('AMAZON', 'amazon_seller', 'encrypted_password_3', 'https://sellercentral.amazon.com/login', 'offline', 92.0, 'Amazon美国站账号'),
    ('MIAOSHOU', 'miaoshou_erp', 'encrypted_password_4', 'https://miaoshou.com/login', 'online', 98.0, '妙手ERP主账号')
ON CONFLICT DO NOTHING;

-- 插入示例数据记录
INSERT INTO data_records (platform, data_type, record_count, quality_score, status) VALUES 
    ('SHOPEE', '商品数据', 2500, 95.0, 'active'),
    ('TIKTOK', '订单数据', 1800, 88.0, 'active'),
    ('AMAZON', '财务数据', 1200, 92.0, 'active'),
    ('MIAOSHOU', '流量数据', 950, 98.0, 'active')
ON CONFLICT DO NOTHING;

-- 创建性能优化索引
CREATE INDEX IF NOT EXISTS idx_accounts_platform ON accounts(platform);
CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status);
CREATE INDEX IF NOT EXISTS idx_data_records_platform ON data_records(platform);
CREATE INDEX IF NOT EXISTS idx_fact_sales_orders_platform ON fact_sales_orders(platform_code);
CREATE INDEX IF NOT EXISTS idx_fact_sales_orders_date ON fact_sales_orders(order_date);
CREATE INDEX IF NOT EXISTS idx_fact_product_metrics_platform ON fact_product_metrics(platform_code);
CREATE INDEX IF NOT EXISTS idx_fact_product_metrics_date ON fact_product_metrics(metric_date);
CREATE INDEX IF NOT EXISTS idx_field_mappings_platform ON field_mappings(platform);
CREATE INDEX IF NOT EXISTS idx_data_files_platform ON data_files(platform);
CREATE INDEX IF NOT EXISTS idx_collection_tasks_platform ON collection_tasks(platform);

-- 显示创建结果
SELECT 
    schemaname,
    tablename,
    'Table created successfully' as status
FROM pg_tables 
WHERE schemaname = 'public' 
ORDER BY tablename;
