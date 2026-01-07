"""添加image_url字段到fact_product_metrics表

Revision ID: 20251105_add_image_url
Revises: 20251105_performance_indexes
Create Date: 2025-11-05

添加图片URL字段到产品指标表，支持产品图片显示
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '20251105_add_image_url'
down_revision = '20251105_performance_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """添加image_url字段"""
    
    # 添加image_url字段到fact_product_metrics表
    op.add_column(
        'fact_product_metrics',
        sa.Column('image_url', sa.String(1024), nullable=True, comment="产品图片URL")
    )
    
    # 添加索引（可选，如果需要按图片筛选）
    op.create_index(
        'ix_metrics_has_image',
        'fact_product_metrics',
        ['platform_code', 'shop_id'],
        postgresql_where=sa.text('image_url IS NOT NULL'),
        unique=False
    )


def downgrade() -> None:
    """删除image_url字段"""
    
    # 删除索引
    op.drop_index('ix_metrics_has_image', table_name='fact_product_metrics')
    
    # 删除字段
    op.drop_column('fact_product_metrics', 'image_url')

