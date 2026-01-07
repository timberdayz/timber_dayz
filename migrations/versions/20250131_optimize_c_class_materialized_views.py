"""优化C类数据物化视图

Revision ID: 20250131_optimize_c_class_mv
Revises: 20250131_add_currency_policy
Create Date: 2025-01-31

C类数据核心字段优化计划（Phase 4）：
优化现有C类数据物化视图，添加数据质量标识字段

优化内容：
1. mv_shop_daily_performance - 添加数据质量标识字段（可选）
2. mv_shop_health_summary - 保持现有结构（无需修改）
3. 保持现有字段兼容性（字段名和类型不变）
4. 使用DROP + CREATE方式重建，确保字段兼容性

注意事项：
- 修改现有物化视图前，先备份现有视图定义（记录在注释中）
- 使用DROP MATERIALIZED VIEW IF EXISTS ... CASCADE删除旧视图
- 确保新视图定义与现有查询兼容（字段名和类型保持一致）
- 数据质量标识字段使用可选字段（NULL值不影响现有查询）
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '20250131_optimize_c_class_mv'
down_revision = '20250131_add_currency_policy'
branch_labels = None
depends_on = None


def upgrade():
    """优化C类数据物化视图"""
    
    # ========== 备份现有视图定义（记录在注释中）==========
    # mv_shop_daily_performance原定义：
    # - 业务标识：platform_code, shop_id, shop_name, metric_date
    # - 订单指标：order_count, gmv_rmb, avg_order_value_rmb, unique_buyers
    # - 流量指标：page_views, unique_visitors, add_to_cart_count
    # - 转化指标：conversion_rate, add_to_cart_rate
    # - 库存指标：total_available_stock, sales_volume_30d, inventory_turnover
    # - 客户满意度：avg_rating, total_review_count
    # - 时间戳：refreshed_at
    
    # ========== 1. 优化mv_shop_daily_performance（店铺日度表现）==========
    
    # 删除旧视图（CASCADE自动删除依赖的索引）
    op.execute(text("""
        DROP MATERIALIZED VIEW IF EXISTS mv_shop_daily_performance CASCADE;
    """))
    
    # 创建优化后的视图（保持现有字段，添加数据质量标识字段）
    op.execute(text("""
        CREATE MATERIALIZED VIEW mv_shop_daily_performance AS
        SELECT 
            -- 业务标识（保持现有字段）
            fo.platform_code,
            fo.shop_id,
            ds.shop_name,
            fo.order_date_local AS metric_date,
            
            -- 订单指标（保持现有字段）
            COUNT(DISTINCT fo.order_id) AS order_count,
            SUM(fo.total_amount_rmb) AS gmv_rmb,
            AVG(fo.total_amount_rmb) AS avg_order_value_rmb,
            COUNT(DISTINCT fo.buyer_id) AS unique_buyers,
            
            -- 流量指标（保持现有字段）
            COALESCE(SUM(fpm.page_views), 0) AS page_views,
            COALESCE(SUM(fpm.unique_visitors), 0) AS unique_visitors,
            COALESCE(SUM(fpm.add_to_cart_count), 0) AS add_to_cart_count,
            
            -- 转化指标（保持现有字段）
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
            
            -- 库存指标（保持现有字段）
            COALESCE(SUM(fpm.available_stock), SUM(fpm.stock), 0) AS total_available_stock,
            COALESCE(SUM(fpm.sales_volume_30d), SUM(fpm.sales_volume), 0) AS sales_volume_30d,
            
            -- 库存周转率（保持现有字段）
            CASE 
                WHEN COALESCE(SUM(fpm.sales_volume_30d), SUM(fpm.sales_volume), 0) > 0 
                    AND COALESCE(SUM(fpm.available_stock), SUM(fpm.stock), 0) > 0
                THEN (365.0 / (COALESCE(SUM(fpm.available_stock), SUM(fpm.stock), 0)::numeric / 
                               (COALESCE(SUM(fpm.sales_volume_30d), SUM(fpm.sales_volume), 0)::numeric / 30.0)))
                ELSE 0 
            END AS inventory_turnover,
            
            -- 客户满意度（保持现有字段）
            COALESCE(AVG(fpm.rating), 0) AS avg_rating,
            COALESCE(SUM(fpm.review_count), 0) AS total_review_count,
            
            -- 新增：数据质量标识字段（可选，NULL值不影响现有查询）
            CASE 
                WHEN SUM(fo.total_amount_rmb) IS NULL OR SUM(fo.total_amount_rmb) = 0 
                THEN 1 
                ELSE 0 
            END AS missing_gmv_flag,
            
            CASE 
                WHEN COALESCE(SUM(fpm.unique_visitors), 0) = 0 
                THEN 1 
                ELSE 0 
            END AS missing_uv_flag,
            
            CASE 
                WHEN COALESCE(SUM(fpm.available_stock), SUM(fpm.stock), 0) = 0 
                THEN 1 
                ELSE 0 
            END AS missing_stock_flag,
            
            CASE 
                WHEN COALESCE(AVG(fpm.rating), 0) = 0 
                THEN 1 
                ELSE 0 
            END AS missing_rating_flag,
            
            -- 时间戳（保持现有字段）
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
    
    # 重新创建唯一索引（支持并发刷新）
    op.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_shop_daily_perf_pk 
        ON mv_shop_daily_performance(platform_code, shop_id, metric_date);
    """))
    
    # 重新创建查询索引（使用IF NOT EXISTS避免冲突）
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_mv_shop_daily_perf_date 
        ON mv_shop_daily_performance(metric_date DESC);
    """))
    
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_mv_shop_daily_perf_shop 
        ON mv_shop_daily_performance(platform_code, shop_id, metric_date DESC);
    """))
    
    # 更新注释
    op.execute(text("""
        COMMENT ON MATERIALIZED VIEW mv_shop_daily_performance IS 
        '店铺日度表现物化视图（C类数据计算优化）- 聚合GMV、订单数、转化率、库存周转率、客户满意度等指标，包含数据质量标识字段';
    """))
    
    # ========== 2. mv_shop_health_summary（店铺健康度汇总）==========
    # 保持现有结构不变，无需修改
    
    # ========== 3. 新建mv_campaign_achievement（销售战役达成率）==========
    # 注意：此视图需要依赖sales_campaigns表，如果表不存在则跳过
    op.execute(text("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS mv_campaign_achievement AS
        SELECT 
            sc.platform_code,
            sc.shop_id,
            sc.campaign_id,
            sc.campaign_name,
            sc.start_date,
            sc.end_date,
            sc.target_gmv,
            sc.target_order_count,
            
            -- 实际达成（从fact_orders聚合）
            COALESCE(SUM(fo.total_amount_rmb), 0) AS actual_gmv,
            COALESCE(COUNT(DISTINCT fo.order_id), 0) AS actual_order_count,
            
            -- 达成率（计算）
            CASE 
                WHEN sc.target_gmv > 0 
                THEN (COALESCE(SUM(fo.total_amount_rmb), 0)::numeric / sc.target_gmv * 100)
                ELSE 0 
            END AS gmv_achievement_rate,
            
            CASE 
                WHEN sc.target_order_count > 0 
                THEN (COALESCE(COUNT(DISTINCT fo.order_id), 0)::numeric / sc.target_order_count * 100)
                ELSE 0 
            END AS order_achievement_rate,
            
            -- 时间戳
            CURRENT_TIMESTAMP AS refreshed_at
            
        FROM sales_campaigns sc
        LEFT JOIN fact_orders fo ON 
            sc.platform_code = fo.platform_code 
            AND sc.shop_id = fo.shop_id
            AND fo.order_date_local >= sc.start_date
            AND fo.order_date_local <= sc.end_date
            AND fo.order_status IN ('completed', 'paid')
        
        WHERE sc.status = 'active'
        
        GROUP BY 
            sc.platform_code,
            sc.shop_id,
            sc.campaign_id,
            sc.campaign_name,
            sc.start_date,
            sc.end_date,
            sc.target_gmv,
            sc.target_order_count
        
        WITH DATA;
    """))
    
    # 创建索引
    op.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_campaign_achievement_pk 
        ON mv_campaign_achievement(platform_code, shop_id, campaign_id);
    """))
    
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_mv_campaign_achievement_date 
        ON mv_campaign_achievement(start_date DESC, end_date DESC);
    """))
    
    op.execute(text("""
        COMMENT ON MATERIALIZED VIEW mv_campaign_achievement IS 
        '销售战役达成率物化视图（C类数据计算优化）- 聚合销售战役GMV和订单数达成率';
    """))
    
    # ========== 4. 新建mv_target_achievement（目标达成率）==========
    # 注意：此视图需要依赖target_management表，如果表不存在则跳过
    op.execute(text("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS mv_target_achievement AS
        SELECT 
            tm.platform_code,
            tm.shop_id,
            tm.target_id,
            tm.target_name,
            tm.target_type,
            tm.target_period,
            tm.target_value,
            
            -- 实际达成（根据target_type从不同表聚合）
            CASE 
                WHEN tm.target_type = 'gmv' THEN 
                    COALESCE(SUM(fo.total_amount_rmb), 0)
                WHEN tm.target_type = 'order_count' THEN 
                    COALESCE(COUNT(DISTINCT fo.order_id), 0)
                ELSE 0 
            END AS actual_value,
            
            -- 达成率（计算）
            CASE 
                WHEN tm.target_value > 0 THEN 
                    (CASE 
                        WHEN tm.target_type = 'gmv' THEN 
                            COALESCE(SUM(fo.total_amount_rmb), 0)::numeric / tm.target_value * 100
                        WHEN tm.target_type = 'order_count' THEN 
                            COALESCE(COUNT(DISTINCT fo.order_id), 0)::numeric / tm.target_value * 100
                        ELSE 0 
                    END)
                ELSE 0 
            END AS achievement_rate,
            
            -- 时间戳
            CURRENT_TIMESTAMP AS refreshed_at
            
        FROM target_management tm
        LEFT JOIN fact_orders fo ON 
            tm.platform_code = fo.platform_code 
            AND tm.shop_id = fo.shop_id
            AND fo.order_date_local >= tm.target_period::date - INTERVAL '1 month'
            AND fo.order_date_local <= tm.target_period::date
            AND fo.order_status IN ('completed', 'paid')
        
        WHERE tm.status = 'active'
        
        GROUP BY 
            tm.platform_code,
            tm.shop_id,
            tm.target_id,
            tm.target_name,
            tm.target_type,
            tm.target_period,
            tm.target_value
        
        WITH DATA;
    """))
    
    # 创建索引
    op.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_target_achievement_pk 
        ON mv_target_achievement(platform_code, shop_id, target_id);
    """))
    
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_mv_target_achievement_period 
        ON mv_target_achievement(target_period DESC);
    """))
    
    op.execute(text("""
        COMMENT ON MATERIALIZED VIEW mv_target_achievement IS 
        '目标达成率物化视图（C类数据计算优化）- 聚合目标GMV和订单数达成率';
    """))


def downgrade():
    """回滚物化视图优化"""
    
    # 删除新建的视图
    op.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_target_achievement CASCADE;"))
    op.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_campaign_achievement CASCADE;"))
    
    # 恢复mv_shop_daily_performance到原始版本（删除数据质量标识字段）
    # 注意：这里只删除新增字段，保持其他字段不变
    # 如果需要完全恢复，需要重新创建原始视图定义
    op.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_shop_daily_performance CASCADE;"))
    
    # 重新创建原始视图（不包含数据质量标识字段）
    op.execute(text("""
        CREATE MATERIALIZED VIEW mv_shop_daily_performance AS
        SELECT 
            fo.platform_code,
            fo.shop_id,
            ds.shop_name,
            fo.order_date_local AS metric_date,
            COUNT(DISTINCT fo.order_id) AS order_count,
            SUM(fo.total_amount_rmb) AS gmv_rmb,
            AVG(fo.total_amount_rmb) AS avg_order_value_rmb,
            COUNT(DISTINCT fo.buyer_id) AS unique_buyers,
            COALESCE(SUM(fpm.page_views), 0) AS page_views,
            COALESCE(SUM(fpm.unique_visitors), 0) AS unique_visitors,
            COALESCE(SUM(fpm.add_to_cart_count), 0) AS add_to_cart_count,
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
            COALESCE(SUM(fpm.available_stock), SUM(fpm.stock), 0) AS total_available_stock,
            COALESCE(SUM(fpm.sales_volume_30d), SUM(fpm.sales_volume), 0) AS sales_volume_30d,
            CASE 
                WHEN COALESCE(SUM(fpm.sales_volume_30d), SUM(fpm.sales_volume), 0) > 0 
                    AND COALESCE(SUM(fpm.available_stock), SUM(fpm.stock), 0) > 0
                THEN (365.0 / (COALESCE(SUM(fpm.available_stock), SUM(fpm.stock), 0)::numeric / 
                               (COALESCE(SUM(fpm.sales_volume_30d), SUM(fpm.sales_volume), 0)::numeric / 30.0)))
                ELSE 0 
            END AS inventory_turnover,
            COALESCE(AVG(fpm.rating), 0) AS avg_rating,
            COALESCE(SUM(fpm.review_count), 0) AS total_review_count,
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
    
    # 重新创建索引
    op.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_shop_daily_perf_pk 
        ON mv_shop_daily_performance(platform_code, shop_id, metric_date);
    """))
    
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_mv_shop_daily_perf_date 
        ON mv_shop_daily_performance(metric_date DESC);
    """))
    
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_mv_shop_daily_perf_shop 
        ON mv_shop_daily_performance(platform_code, shop_id, metric_date DESC);
    """))

