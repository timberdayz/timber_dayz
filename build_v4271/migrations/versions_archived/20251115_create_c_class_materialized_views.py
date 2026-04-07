"""创建C类数据计算物化视图

Revision ID: 20251115_c_class_mv
Revises: 20251115_c_class_indexes
Create Date: 2025-11-15

创建物化视图以优化C类数据查询性能：
1. mv_shop_daily_performance - 店铺日度表现（GMV、订单数、转化率等）
2. mv_shop_health_summary - 店铺健康度汇总（健康度评分、各项得分等）
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '20251115_c_class_mv'
down_revision = '20251115_c_class_indexes'
branch_labels = None
depends_on = None


def upgrade():
    """创建C类数据计算物化视图"""
    
    # ========== 1. mv_shop_daily_performance（店铺日度表现） ==========
    
    op.execute(text("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS mv_shop_daily_performance AS
        SELECT 
            -- 业务标识
            fo.platform_code,
            fo.shop_id,
            ds.shop_name,
            fo.order_date_local AS metric_date,
            
            -- 订单指标（从fact_orders聚合）
            COUNT(DISTINCT fo.order_id) AS order_count,
            SUM(fo.total_amount_rmb) AS gmv_rmb,
            AVG(fo.total_amount_rmb) AS avg_order_value_rmb,
            COUNT(DISTINCT fo.buyer_id) AS unique_buyers,
            
            -- 流量指标（从fact_product_metrics聚合）
            COALESCE(SUM(fpm.page_views), 0) AS page_views,
            COALESCE(SUM(fpm.unique_visitors), 0) AS unique_visitors,
            COALESCE(SUM(fpm.add_to_cart_count), 0) AS add_to_cart_count,
            
            -- 转化指标（计算）
            CASE 
                WHEN COALESCE(SUM(fpm.unique_visitors), 0) > 0 
                THEN (COUNT(DISTINCT fo.order_id)::numeric / SUM(fpm.unique_visitors) * 100)
                ELSE 0 
            END AS conversion_rate,
            
            CASE 
                WHEN COALESCE(SUM(fpm.unique_visitors), 0) > 0 
                THEN (SUM(fpm.add_to_cart_count)::numeric / SUM(fpm.unique_visitors) * 100)
                ELSE 0 
            END AS add_to_cart_rate,
            
            -- 库存指标（从fact_product_metrics聚合）
            COALESCE(SUM(fpm.available_stock), SUM(fpm.stock), 0) AS total_available_stock,
            COALESCE(SUM(fpm.sales_volume_30d), SUM(fpm.sales_volume), 0) AS sales_volume_30d,
            
            -- 库存周转率（计算）
            CASE 
                WHEN COALESCE(SUM(fpm.sales_volume_30d), SUM(fpm.sales_volume), 0) > 0 
                    AND COALESCE(SUM(fpm.available_stock), SUM(fpm.stock), 0) > 0
                THEN (365.0 / (COALESCE(SUM(fpm.available_stock), SUM(fpm.stock), 0)::numeric / 
                               (COALESCE(SUM(fpm.sales_volume_30d), SUM(fpm.sales_volume), 0)::numeric / 30.0)))
                ELSE 0 
            END AS inventory_turnover,
            
            -- 客户满意度（从fact_product_metrics聚合）
            COALESCE(AVG(fpm.rating), 0) AS avg_rating,
            COALESCE(SUM(fpm.review_count), 0) AS total_review_count,
            
            -- 时间戳
            CURRENT_TIMESTAMP AS refreshed_at
            
        FROM fact_orders fo
        LEFT JOIN dim_shops ds ON fo.platform_code = ds.platform_code AND fo.shop_id = ds.shop_id
        LEFT JOIN fact_product_metrics fpm ON 
            fo.platform_code = fpm.platform_code 
            AND fo.shop_id = fpm.shop_id 
            AND fo.order_date_local = fpm.metric_date
            AND COALESCE(fpm.data_domain, 'products') = 'products'
            AND fpm.granularity = 'daily'
        
        WHERE fo.order_status IN ('completed', 'paid')
          AND fo.order_date_local >= CURRENT_DATE - INTERVAL '90 days'
        
        GROUP BY 
            fo.platform_code,
            fo.shop_id,
            ds.shop_name,
            fo.order_date_local
        
        WITH DATA;
    """))
    
    # 创建唯一索引（支持并发刷新）
    op.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_shop_daily_perf_pk 
        ON mv_shop_daily_performance(platform_code, shop_id, metric_date);
    """))
    
    # 创建查询索引
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_mv_shop_daily_perf_date 
        ON mv_shop_daily_performance(metric_date DESC);
    """))
    
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_mv_shop_daily_perf_shop 
        ON mv_shop_daily_performance(platform_code, shop_id, metric_date DESC);
    """))
    
    op.execute(text("""
        COMMENT ON MATERIALIZED VIEW mv_shop_daily_performance IS 
        '店铺日度表现物化视图（C类数据计算优化）- 聚合GMV、订单数、转化率、库存周转率、客户满意度等指标';
    """))
    
    # ========== 2. mv_shop_health_summary（店铺健康度汇总） ==========
    
    op.execute(text("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS mv_shop_health_summary AS
        SELECT 
            -- 业务标识
            shs.platform_code,
            shs.shop_id,
            ds.shop_name,
            shs.metric_date,
            shs.granularity,
            
            -- 健康度评分
            shs.health_score,
            shs.gmv_score,
            shs.conversion_score,
            shs.inventory_score,
            shs.service_score,
            
            -- 基础指标
            shs.gmv,
            shs.conversion_rate,
            shs.inventory_turnover,
            shs.customer_satisfaction,
            
            -- 风险等级
            shs.risk_level,
            shs.risk_factors,
            
            -- 排名（基于健康度评分）
            ROW_NUMBER() OVER (
                PARTITION BY shs.metric_date, shs.granularity 
                ORDER BY shs.health_score DESC
            ) AS health_rank,
            
            -- 时间戳
            shs.created_at,
            shs.updated_at
            
        FROM shop_health_scores shs
        LEFT JOIN dim_shops ds ON shs.platform_code = ds.platform_code AND shs.shop_id = ds.shop_id
        
        WHERE shs.metric_date >= CURRENT_DATE - INTERVAL '90 days'
        
        WITH DATA;
    """))
    
    # 创建唯一索引（支持并发刷新）
    op.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_shop_health_summary_pk 
        ON mv_shop_health_summary(platform_code, shop_id, metric_date, granularity);
    """))
    
    # 创建查询索引
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_mv_shop_health_summary_date 
        ON mv_shop_health_summary(metric_date DESC, granularity);
    """))
    
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_mv_shop_health_summary_rank 
        ON mv_shop_health_summary(metric_date, granularity, health_rank);
    """))
    
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_mv_shop_health_summary_risk 
        ON mv_shop_health_summary(risk_level, metric_date DESC);
    """))
    
    op.execute(text("""
        COMMENT ON MATERIALIZED VIEW mv_shop_health_summary IS 
        '店铺健康度汇总物化视图（C类数据计算优化）- 聚合健康度评分、各项得分、风险等级、排名等指标';
    """))


def downgrade():
    """删除物化视图"""
    
    op.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_shop_health_summary CASCADE;"))
    op.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_shop_daily_performance CASCADE;"))

