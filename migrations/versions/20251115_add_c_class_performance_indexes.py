"""添加C类数据计算性能优化索引

Revision ID: 20251115_c_class_indexes
Revises: 
Create Date: 2025-11-15

添加索引以优化C类数据计算查询性能：
1. fact_orders表：日期范围查询、状态筛选、店铺统计
2. fact_product_metrics表：数据域筛选、粒度筛选、健康度计算
3. shop_health_scores表：日期查询、排名查询
4. clearance_rankings表：排名查询优化
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '20251115_c_class_indexes'
down_revision = 'v4_11_0_sales_campaign_target'  # 基于v4.11.0销售战役和目标管理迁移
branch_labels = None
depends_on = None


def upgrade():
    """添加C类数据计算性能优化索引"""
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # ========== fact_orders表索引优化 ==========
    
    # 检查fact_orders表的索引
    fact_orders_indexes = [idx['name'] for idx in inspector.get_indexes('fact_orders')]
    
    # 1. 日期范围查询索引（用于达成率计算：按日期范围聚合）
    if 'ix_orders_date_range' not in fact_orders_indexes:
        op.create_index(
            'ix_orders_date_range',
            'fact_orders',
            ['order_date_local', 'platform_code', 'shop_id'],
            unique=False,
            postgresql_where=text("order_status IN ('completed', 'paid')")
        )
    
    # 2. 店铺+日期+状态复合索引（用于店铺赛马排名和达成率计算）
    if 'ix_orders_shop_date_status' not in fact_orders_indexes:
        op.create_index(
            'ix_orders_shop_date_status',
            'fact_orders',
            ['shop_id', 'order_date_local', 'order_status'],
            unique=False
        )
    
    # 3. 平台+日期+状态索引（用于平台级统计）
    if 'ix_orders_platform_date_status' not in fact_orders_indexes:
        op.create_index(
            'ix_orders_platform_date_status',
            'fact_orders',
            ['platform_code', 'order_date_local', 'order_status'],
            unique=False
        )
    
    # ========== fact_product_metrics表索引优化 ==========
    
    # 检查fact_product_metrics表的索引
    fact_product_metrics_indexes = [idx['name'] for idx in inspector.get_indexes('fact_product_metrics')]
    
    # 4. 数据域+日期索引（用于products域查询，健康度计算）
    if 'ix_metrics_domain_date' not in fact_product_metrics_indexes:
        op.create_index(
            'ix_metrics_domain_date',
            'fact_product_metrics',
            ['data_domain', 'metric_date', 'platform_code', 'shop_id'],
            unique=False
        )
    
    # 5. 粒度索引（用于按粒度筛选）
    # 注意：如果之前的迁移已经创建了ix_metrics_granularity索引（只包含granularity列），
    # 我们需要先删除旧索引，然后创建新的复合索引
    if 'ix_metrics_granularity' in fact_product_metrics_indexes:
        # 检查现有索引的列
        existing_idx = next((idx for idx in inspector.get_indexes('fact_product_metrics') if idx['name'] == 'ix_metrics_granularity'), None)
        if existing_idx and len(existing_idx.get('column_names', [])) == 1:
            # 旧索引只包含granularity列，需要删除并重新创建
            print("[INFO] 删除旧的ix_metrics_granularity索引（只包含granularity列）")
            op.drop_index('ix_metrics_granularity', table_name='fact_product_metrics')
        
    if 'ix_metrics_granularity' not in [idx['name'] for idx in inspector.get_indexes('fact_product_metrics')]:
        op.create_index(
            'ix_metrics_granularity',
            'fact_product_metrics',
            ['granularity', 'metric_date'],
            unique=False
        )
    
    # 6. 库存周转率计算索引（available_stock + sales_volume_30d）
    if 'ix_metrics_inventory_turnover' not in fact_product_metrics_indexes:
        op.create_index(
            'ix_metrics_inventory_turnover',
            'fact_product_metrics',
            ['platform_code', 'shop_id', 'available_stock', 'sales_volume_30d'],
            unique=False,
            postgresql_where=text("data_domain IN ('products', 'inventory')")
        )
    
    # 7. 客户满意度计算索引（rating字段）
    if 'ix_metrics_rating' not in fact_product_metrics_indexes:
        op.create_index(
            'ix_metrics_rating',
            'fact_product_metrics',
            ['platform_code', 'shop_id', 'metric_date', 'rating'],
            unique=False,
            postgresql_where=text("data_domain = 'products' AND rating IS NOT NULL AND rating > 0")
        )
    
    # ========== shop_health_scores表索引优化 ==========
    
    # 检查shop_health_scores表的索引
    shop_health_scores_indexes = [idx['name'] for idx in inspector.get_indexes('shop_health_scores')]
    
    # 8. 日期+粒度索引（用于历史趋势查询）
    if 'ix_health_scores_date_granularity' not in shop_health_scores_indexes:
        op.create_index(
            'ix_health_scores_date_granularity',
            'shop_health_scores',
            ['metric_date', 'granularity', 'platform_code', 'shop_id'],
            unique=False
        )
    
    # 9. 健康度排名索引（用于排名查询）
    if 'ix_health_scores_rank' not in shop_health_scores_indexes:
        op.create_index(
            'ix_health_scores_rank',
            'shop_health_scores',
            ['metric_date', 'health_score'],
            unique=False,
            postgresql_ops={'health_score': 'DESC'}
        )
    
    # ========== clearance_rankings表索引优化 ==========
    
    # 检查clearance_rankings表的索引
    clearance_rankings_indexes = [idx['name'] for idx in inspector.get_indexes('clearance_rankings')]
    
    # 10. 排名查询索引（用于滞销清理排名）
    if 'ix_clearance_rankings_date_rank' not in clearance_rankings_indexes:
        op.create_index(
            'ix_clearance_rankings_date_rank',
            'clearance_rankings',
            ['metric_date', 'granularity', 'rank'],
            unique=False
        )
    
    # 11. 清理金额索引（用于排序）
    if 'ix_clearance_rankings_amount' not in clearance_rankings_indexes:
        op.create_index(
            'ix_clearance_rankings_amount',
            'clearance_rankings',
            ['metric_date', 'clearance_amount'],
            unique=False,
            postgresql_ops={'clearance_amount': 'DESC'}
        )
    
    # ========== sales_campaigns和targets表索引优化 ==========
    
    # 检查sales_campaigns表的索引
    sales_campaigns_indexes = [idx['name'] for idx in inspector.get_indexes('sales_campaigns')]
    
    # 12. 销售战役日期范围索引（用于查询活跃战役）
    if 'ix_campaigns_date_range' not in sales_campaigns_indexes:
        op.create_index(
            'ix_campaigns_date_range',
            'sales_campaigns',
            ['start_date', 'end_date', 'status'],
            unique=False
        )
    
    # 检查sales_targets表的索引
    sales_targets_indexes = [idx['name'] for idx in inspector.get_indexes('sales_targets')]
    
    # 13. 目标日期范围索引（用于查询活跃目标）
    if 'ix_targets_date_range' not in sales_targets_indexes:
        op.create_index(
            'ix_targets_date_range',
            'sales_targets',
            ['period_start', 'period_end', 'status'],
            unique=False
        )


def downgrade():
    """回滚索引创建"""
    
    # 删除所有创建的索引
    op.drop_index('ix_orders_date_range', table_name='fact_orders')
    op.drop_index('ix_orders_shop_date_status', table_name='fact_orders')
    op.drop_index('ix_orders_platform_date_status', table_name='fact_orders')
    
    op.drop_index('ix_metrics_domain_date', table_name='fact_product_metrics')
    op.drop_index('ix_metrics_granularity', table_name='fact_product_metrics')
    op.drop_index('ix_metrics_inventory_turnover', table_name='fact_product_metrics')
    op.drop_index('ix_metrics_rating', table_name='fact_product_metrics')
    
    op.drop_index('ix_health_scores_date_granularity', table_name='shop_health_scores')
    op.drop_index('ix_health_scores_rank', table_name='shop_health_scores')
    
    op.drop_index('ix_clearance_rankings_date_rank', table_name='clearance_rankings')
    op.drop_index('ix_clearance_rankings_amount', table_name='clearance_rankings')
    
    op.drop_index('ix_campaigns_date_range', table_name='sales_campaigns')
    op.drop_index('ix_targets_date_range', table_name='sales_targets')

