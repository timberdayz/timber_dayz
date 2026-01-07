"""v4.12.0: Add product_id to FactOrderItem for atomic-level queries

Revision ID: 20251120_172442
Revises: 20250131_v4_6_0_pattern_based_mapping
Create Date: 2025-11-20 17:24:42.000000

Changes:
1. 添加product_id字段到fact_order_items表（冗余字段，便于直接查询）
2. 创建product_id索引（支持高效查询）
3. 支持以product_id为原子级的销售明细查询

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251120_172442'
down_revision = 'v4_6_0'
branch_labels = None
depends_on = None


def upgrade():
    """Add product_id field to fact_order_items table"""
    
    # 1. 添加product_id字段（允许NULL，冗余字段）
    op.add_column(
        'fact_order_items',
        sa.Column(
            'product_id',
            sa.Integer(),
            nullable=True,
            comment='产品ID（冗余字段，通过BridgeProductKeys自动关联）'
        )
    )
    
    # 2. 添加外键约束（引用dim_product_master.product_id）
    op.create_foreign_key(
        'fk_fact_order_items_product_id',
        'fact_order_items',
        'dim_product_master',
        ['product_id'],
        ['product_id'],
        ondelete='SET NULL'
    )
    
    # 3. 创建索引（支持高效查询）
    op.create_index(
        'ix_fact_items_product_id',
        'fact_order_items',
        ['product_id'],
        unique=False
    )


def downgrade():
    """Remove product_id field from fact_order_items table"""
    
    # 1. 删除索引
    op.drop_index('ix_fact_items_product_id', table_name='fact_order_items')
    
    # 2. 删除外键约束
    op.drop_constraint('fk_fact_order_items_product_id', 'fact_order_items', type_='foreignkey')
    
    # 3. 删除字段
    op.drop_column('fact_order_items', 'product_id')

