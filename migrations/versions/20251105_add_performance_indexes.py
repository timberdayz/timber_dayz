"""添加性能优化索引

Revision ID: 20251105_performance_indexes
Revises: 
Create Date: 2025-11-05

添加8个关键索引以优化查询性能：
1. 字段辞典复合索引（data_domain + version + status）
2. 字段辞典Pattern索引
3. 订单日期+平台索引
4. 订单店铺+日期索引
5. 订单状态索引
6. 产品指标日期范围索引
7. 产品SKU索引
8. 产品粒度索引
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251105_performance_indexes'
down_revision = None  # 或设置为上一个迁移的revision
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建性能优化索引"""
    
    # 1. 字段辞典复合索引
    op.create_index(
        'ix_field_dict_composite',
        'field_mapping_dictionary',
        ['data_domain', 'version', 'status'],
        unique=False
    )
    
    # 2. 字段辞典Pattern索引
    op.create_index(
        'ix_field_dict_pattern',
        'field_mapping_dictionary',
        ['is_pattern_based'],
        unique=False
    )
    
    # 3. 订单日期+平台复合索引
    op.create_index(
        'ix_orders_date_platform',
        'fact_orders',
        ['order_date_local', 'platform_code'],
        unique=False
    )
    
    # 4. 订单店铺+日期索引
    op.create_index(
        'ix_orders_shop_date',
        'fact_orders',
        ['shop_id', 'order_date_local'],
        unique=False
    )
    
    # 5. 订单状态索引
    op.create_index(
        'ix_orders_status',
        'fact_orders',
        ['order_status'],
        unique=False
    )
    
    # 6. 产品指标日期范围索引
    op.create_index(
        'ix_metrics_date_range',
        'fact_product_metrics',
        ['metric_date', 'platform_code', 'shop_id'],
        unique=False
    )
    
    # 7. 产品SKU索引
    op.create_index(
        'ix_metrics_sku_date',
        'fact_product_metrics',
        ['platform_sku', 'metric_date'],
        unique=False
    )
    
    # 8. 产品粒度索引
    op.create_index(
        'ix_metrics_granularity',
        'fact_product_metrics',
        ['granularity'],
        unique=False
    )


def downgrade() -> None:
    """删除性能优化索引"""
    
    # 按创建顺序反向删除
    op.drop_index('ix_metrics_granularity', table_name='fact_product_metrics')
    op.drop_index('ix_metrics_sku_date', table_name='fact_product_metrics')
    op.drop_index('ix_metrics_date_range', table_name='fact_product_metrics')
    op.drop_index('ix_orders_status', table_name='fact_orders')
    op.drop_index('ix_orders_shop_date', table_name='fact_orders')
    op.drop_index('ix_orders_date_platform', table_name='fact_orders')
    op.drop_index('ix_field_dict_pattern', table_name='field_mapping_dictionary')
    op.drop_index('ix_field_dict_composite', table_name='field_mapping_dictionary')

