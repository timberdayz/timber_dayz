"""v4.18.1: 添加shop_id字段到platform_accounts表

Revision ID: 20260101_shop_id
Revises: 20251216_component_versions
Create Date: 2026-01-01

优化：添加shop_id字段，用于关联数据同步中的店铺标识
- 用户可以在账号管理页面手动编辑shop_id
- 用于Metabase模型中关联数据同步的shop_id和店铺名称
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260101_shop_id'
down_revision = '20251216_component_versions'
branch_labels = None
depends_on = None


def upgrade():
    """添加shop_id字段和索引"""
    # 添加shop_id列
    op.add_column(
        'platform_accounts',
        sa.Column(
            'shop_id',
            sa.String(length=256),
            nullable=True,
            comment='店铺ID（用于关联数据同步中的shop_id，可编辑）'
        )
    )
    
    # 创建索引
    op.create_index(
        'ix_platform_accounts_shop_id',
        'platform_accounts',
        ['shop_id'],
        unique=False
    )


def downgrade():
    """移除shop_id字段和索引"""
    op.drop_index('ix_platform_accounts_shop_id', table_name='platform_accounts')
    op.drop_column('platform_accounts', 'shop_id')

