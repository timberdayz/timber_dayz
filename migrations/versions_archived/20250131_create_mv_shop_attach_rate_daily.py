"""创建店铺日度连带率物化视图

Revision ID: 20250131_mv_attach_rate
Revises: 20250131_optimize_c_class_mv
Create Date: 2025-01-31

v4.11.5新增：创建店铺日度连带率物化视图
连带率指标增强计划（中优先级）

创建物化视图：
- mv_shop_attach_rate_daily - 店铺日度连带率（订单项数/订单数）
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '20250131_mv_attach_rate'
down_revision = '20250131_optimize_c_class_mv'
branch_labels = None
depends_on = None


def upgrade():
    """创建店铺日度连带率物化视图"""
    
    op.execute(text("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS mv_shop_attach_rate_daily AS
        SELECT 
            -- 业务标识
            fo.platform_code,
            fo.shop_id,
            ds.shop_name,
            fo.order_date_local AS metric_date,
            
            -- 订单统计
            COUNT(DISTINCT fo.order_id) AS order_count,
            COUNT(DISTINCT fo.buyer_id) AS unique_buyers,
            
            -- 订单项统计（从fact_order_items统计）
            SUM(COALESCE(item_stats.item_count, 0)) AS item_count,
            
            -- 连带率计算（订单项数 / 订单数）
            CASE 
                WHEN COUNT(DISTINCT fo.order_id) > 0 
                THEN ROUND((SUM(COALESCE(item_stats.item_count, 0))::numeric / COUNT(DISTINCT fo.order_id)::numeric), 2)
                ELSE 0 
            END AS attach_rate,
            
            -- 订单金额统计（用于分析）
            SUM(fo.total_amount_rmb) AS gmv_rmb,
            AVG(fo.total_amount_rmb) AS avg_order_value_rmb,
            
            -- 时间戳
            CURRENT_TIMESTAMP AS refreshed_at
            
        FROM fact_orders fo
        LEFT JOIN dim_shops ds ON fo.platform_code = ds.platform_code AND fo.shop_id = ds.shop_id
        LEFT JOIN (
            SELECT 
                platform_code,
                shop_id,
                order_id,
                COUNT(*) AS item_count
            FROM fact_order_items
            GROUP BY platform_code, shop_id, order_id
        ) item_stats ON 
            item_stats.platform_code = fo.platform_code
            AND item_stats.shop_id = fo.shop_id
            AND item_stats.order_id = fo.order_id
        
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
        CREATE UNIQUE INDEX IF NOT EXISTS ix_mv_attach_rate_shop_date 
        ON mv_shop_attach_rate_daily (platform_code, shop_id, metric_date);
    """))
    
    # 创建查询索引
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_mv_attach_rate_date 
        ON mv_shop_attach_rate_daily (metric_date);
    """))
    
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_mv_attach_rate_platform 
        ON mv_shop_attach_rate_daily (platform_code, metric_date);
    """))
    
    print("[MV] 物化视图mv_shop_attach_rate_daily创建成功")


def downgrade():
    """删除店铺日度连带率物化视图"""
    op.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_shop_attach_rate_daily CASCADE;"))
    print("[MV] 物化视图mv_shop_attach_rate_daily已删除")

