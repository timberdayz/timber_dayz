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
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # 检查列是否已存在
    existing_columns = [col['name'] for col in inspector.get_columns('fact_product_metrics')]
    
    if 'image_url' not in existing_columns:
        # 添加image_url字段到fact_product_metrics表
        op.add_column(
            'fact_product_metrics',
            sa.Column('image_url', sa.String(1024), nullable=True, comment="产品图片URL")
        )
        print("[OK] 添加image_url字段到fact_product_metrics表")
    else:
        print("[INFO] image_url字段已存在，跳过添加")
    
    # 检查索引是否已存在
    existing_indexes = [idx['name'] for idx in inspector.get_indexes('fact_product_metrics')]
    
    if 'ix_metrics_has_image' not in existing_indexes:
        # 添加索引（可选，如果需要按图片筛选）
        op.create_index(
            'ix_metrics_has_image',
            'fact_product_metrics',
            ['platform_code', 'shop_id'],
            postgresql_where=sa.text('image_url IS NOT NULL'),
            unique=False
        )
        print("[OK] 添加ix_metrics_has_image索引")
    else:
        print("[INFO] ix_metrics_has_image索引已存在，跳过创建")


def downgrade() -> None:
    """删除image_url字段"""
    
    # 删除索引
    op.drop_index('ix_metrics_has_image', table_name='fact_product_metrics')
    
    # 删除字段
    op.drop_column('fact_product_metrics', 'image_url')

