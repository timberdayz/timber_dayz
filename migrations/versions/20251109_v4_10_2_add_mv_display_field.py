"""v4.10.2: Add is_mv_display field to FieldMappingDictionary

Revision ID: v4_10_2
Revises: 20251105_add_performance_indexes
Create Date: 2025-11-09 20:35:00.000000

Changes:
1. 新增字段：
   - field_mapping_dictionary.is_mv_display: 标识字段是否需要在物化视图中显示

2. 功能改进：
   - 支持标注物化视图核心字段
   - 优化物化视图性能（只包含必要字段）
   - 提高数据质量管理效率

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'v4_10_2'
down_revision = '20251105_performance_indexes'
branch_labels = None
depends_on = None


def upgrade():
    """Apply v4.10.2 schema changes"""
    
    # 添加is_mv_display字段到field_mapping_dictionary表
    op.add_column('field_mapping_dictionary', 
                  sa.Column('is_mv_display', sa.Boolean(), nullable=False, 
                           server_default='false', 
                           comment='是否需要在物化视图中显示（true=核心字段，false=辅助字段）'))
    
    # 创建索引（用于快速查询物化视图需要的字段）
    op.create_index('ix_dictionary_mv_display', 'field_mapping_dictionary', 
                    ['is_mv_display', 'data_domain'], unique=False)
    
    # 初始化核心字段的is_mv_display值（必填字段和关键维度字段默认true）
    op.execute("""
        UPDATE field_mapping_dictionary 
        SET is_mv_display = true 
        WHERE is_required = true 
           OR field_group IN ('dimension', 'amount', 'quantity')
           OR field_code IN (
               'order_id', 'platform_code', 'shop_id', 'order_time_utc', 'order_date_local',
               'currency', 'subtotal', 'total_amount', 'shipping_fee', 'tax_amount',
               'platform_sku', 'product_name', 'sales_volume', 'sales_amount_rmb',
               'metric_date', 'granularity'
           )
    """)


def downgrade():
    """Revert v4.10.2 schema changes"""
    
    # 删除索引
    op.drop_index('ix_dictionary_mv_display', table_name='field_mapping_dictionary')
    
    # 删除字段
    op.drop_column('field_mapping_dictionary', 'is_mv_display')

