"""create materialized view for product management

Revision ID: 20251105_204106
Revises: 20251105_add_field_usage_tracking
Create Date: 2025-11-05 20:41:06

企业级ERP语义层实施 - v4.8.0
参考SAP BW InfoCube和Oracle Materialized View设计标准

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = '20251105_204106'
down_revision = 'add_field_usage_tracking'
branch_labels = None
depends_on = None


def upgrade():
    """
    创建产品管理物化视图（mv_product_management）
    
    目标：
    1. 预JOIN维度表（dim_platforms, dim_shops）
    2. 预计算业务指标（库存状态、转化率、预估营收）
    3. 提升查询性能10-100倍
    
    设计原则：
    - Single Source of Truth: 视图定义在此唯一位置
    - 企业级标准: 参考SAP HANA Views和Oracle MV
    - 性能优先: CONCURRENTLY刷新（不锁表）
    """
    
    # 创建产品管理物化视图
    op.execute(text("""
        CREATE MATERIALIZED VIEW mv_product_management AS
        SELECT 
            -- ========== 主键和标识 ==========
            p.id as metric_id,
            p.platform_code,
            plat.platform_name,
            p.shop_id,
            s.shop_name,
            
            -- ========== 产品基本信息 ==========
            p.platform_sku,
            p.product_name,
            p.category,
            p.brand,
            p.product_link,
            p.image_url,
            
            -- ========== 价格信息 ==========
            p.price,
            p.currency,
            p.price_rmb,
            p.original_price,
            p.discount_rate,
            
            -- ========== 库存信息 ==========
            p.stock,
            p.available_stock,
            p.total_stock,
            -- 计算字段：库存状态（业务逻辑集中管理）
            CASE 
                WHEN COALESCE(p.available_stock, p.stock, 0) = 0 THEN 'out_of_stock'
                WHEN COALESCE(p.available_stock, p.stock, 0) < 10 THEN 'low_stock'
                WHEN COALESCE(p.available_stock, p.stock, 0) < 50 THEN 'medium_stock'
                ELSE 'high_stock'
            END as stock_status,
            
            -- ========== 销售指标 ==========
            p.sales_volume,
            p.sales_amount,
            p.sales_amount_rmb,
            p.revenue,
            p.revenue_rmb,
            
            -- ========== 流量指标 ==========
            p.page_views,
            p.visitors,
            p.add_to_cart_count,
            p.wishlist_count,
            
            -- 计算字段：转化率（业务逻辑）
            CASE 
                WHEN COALESCE(p.page_views, 0) > 0 
                THEN ROUND((p.sales_volume::numeric / p.page_views * 100), 2)
                ELSE 0
            END as conversion_rate_calc,
            
            -- 计算字段：加购率
            CASE 
                WHEN COALESCE(p.page_views, 0) > 0 
                THEN ROUND((p.add_to_cart_count::numeric / p.page_views * 100), 2)
                ELSE 0
            END as add_to_cart_rate,
            
            -- ========== 评价指标 ==========
            p.rating,
            p.review_count,
            p.positive_review_rate,
            
            -- ========== 状态和时间 ==========
            p.status,
            p.listing_status,
            p.metric_date,
            p.granularity,
            p.period_start,
            p.period_end,
            
            -- ========== 计算字段（业务价值）==========
            -- 预估营收（CNY）
            p.sales_volume * COALESCE(p.price_rmb, p.price, 0) as estimated_revenue_rmb,
            
            -- 库存周转天数（假设）
            CASE 
                WHEN COALESCE(p.sales_volume, 0) > 0 
                THEN ROUND((p.stock::numeric / (p.sales_volume::numeric / 30)), 1)
                ELSE 999
            END as inventory_turnover_days,
            
            -- 产品健康度评分（0-100）
            LEAST(100, GREATEST(0,
                COALESCE(p.rating, 0) * 20 +  -- 评分占20分
                CASE WHEN p.stock > 0 THEN 20 ELSE 0 END +  -- 有库存20分
                LEAST(20, COALESCE(p.sales_volume, 0) / 10) +  -- 销量占20分
                LEAST(20, COALESCE(p.page_views, 0) / 100) +  -- 流量占20分
                CASE WHEN p.status = 'active' THEN 20 ELSE 0 END  -- 在售20分
            )) as product_health_score,
            
            -- ========== 审计字段 ==========
            p.created_at,
            p.updated_at,
            p.data_quality_score,
            
            -- ========== 元数据 ==========
            p.attributes  -- JSONB扩展字段
            
        FROM fact_product_metrics p
        LEFT JOIN dim_platforms plat ON p.platform_code = plat.platform_code
        LEFT JOIN dim_shops s ON p.platform_code = s.platform_code AND p.shop_id = s.shop_id
        
        -- 性能优化：只保留最近90天数据
        WHERE p.metric_date >= CURRENT_DATE - INTERVAL '90 days'
        
        WITH DATA;
    """))
    
    print("[MV] 物化视图mv_product_management创建成功")
    
    # 创建唯一索引（必须有，支持CONCURRENTLY刷新）
    op.execute(text("""
        CREATE UNIQUE INDEX idx_mv_product_management_pk 
        ON mv_product_management(metric_id);
    """))
    print("[MV] 唯一索引创建成功")
    
    # 创建筛选索引（提升查询性能）
    op.execute(text("""
        CREATE INDEX idx_mv_product_platform 
        ON mv_product_management(platform_code);
    """))
    
    op.execute(text("""
        CREATE INDEX idx_mv_product_category 
        ON mv_product_management(category);
    """))
    
    op.execute(text("""
        CREATE INDEX idx_mv_product_stock_status 
        ON mv_product_management(stock_status);
    """))
    
    op.execute(text("""
        CREATE INDEX idx_mv_product_status 
        ON mv_product_management(status);
    """))
    
    op.execute(text("""
        CREATE INDEX idx_mv_product_date 
        ON mv_product_management(metric_date DESC);
    """))
    
    # 组合索引：平台+SKU（常用查询）
    op.execute(text("""
        CREATE INDEX idx_mv_product_platform_sku 
        ON mv_product_management(platform_code, platform_sku);
    """))
    
    print("[MV] 所有索引创建成功")
    
    # 创建刷新函数
    op.execute(text("""
        CREATE OR REPLACE FUNCTION refresh_product_management_view()
        RETURNS TABLE(
            duration_seconds FLOAT,
            row_count INTEGER,
            success BOOLEAN
        ) AS $$
        DECLARE
            start_time TIMESTAMP;
            end_time TIMESTAMP;
            duration FLOAT;
            rows INTEGER;
        BEGIN
            start_time := clock_timestamp();
            
            -- 刷新物化视图（CONCURRENTLY不锁表）
            REFRESH MATERIALIZED VIEW CONCURRENTLY mv_product_management;
            
            end_time := clock_timestamp();
            duration := EXTRACT(EPOCH FROM (end_time - start_time));
            
            -- 获取行数
            SELECT COUNT(*) INTO rows FROM mv_product_management;
            
            RETURN QUERY SELECT duration, rows, true;
        END;
        $$ LANGUAGE plpgsql;
    """))
    print("[MV] 刷新函数创建成功")


def downgrade():
    """
    回滚：删除物化视图和相关对象
    """
    # 删除刷新函数
    op.execute(text("DROP FUNCTION IF EXISTS refresh_product_management_view();"))
    
    # 删除物化视图（CASCADE删除所有依赖）
    op.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_product_management CASCADE;"))
    
    print("[MV] 物化视图已删除")

