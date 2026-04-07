"""Phase 9.2: 添加增量采集同步点表

Revision ID: 20251216_sync_points
Revises: 20251214_account_alias
Create Date: 2025-12-16

增量采集支持：记录每个账号+数据域的最后采集时间点
预期收益：产品/库存采集速度提升10倍+
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '20251216_sync_points'
down_revision = '20251214_account_alias'
branch_labels = None
depends_on = None


def upgrade():
    """创建collection_sync_points表"""
    op.create_table(
        'collection_sync_points',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('platform', sa.String(length=50), nullable=False, comment='平台代码'),
        sa.Column('account_id', sa.String(length=100), nullable=False, comment='账号ID'),
        sa.Column('data_domain', sa.String(length=50), nullable=False, comment='数据域: orders/products/inventory/traffic/services'),
        sa.Column('last_sync_at', sa.DateTime(), nullable=False, comment='最后同步时间（UTC）'),
        sa.Column('last_sync_value', sa.String(length=200), nullable=True, comment='最后同步值（如最大的updated_at时间戳）'),
        sa.Column('total_synced_count', sa.Integer(), nullable=True, comment='累计同步记录数'),
        sa.Column('last_batch_count', sa.Integer(), nullable=True, comment='最近一次同步记录数'),
        sa.Column('sync_mode', sa.String(length=20), nullable=True, comment='同步模式: full/incremental'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('platform', 'account_id', 'data_domain', name='uq_sync_point')
    )
    
    # 创建索引
    op.create_index(
        'ix_sync_points_platform_account',
        'collection_sync_points',
        ['platform', 'account_id']
    )
    op.create_index(
        'ix_sync_points_last_sync',
        'collection_sync_points',
        ['last_sync_at']
    )


def downgrade():
    """删除collection_sync_points表"""
    op.drop_index('ix_sync_points_last_sync', table_name='collection_sync_points')
    op.drop_index('ix_sync_points_platform_account', table_name='collection_sync_points')
    op.drop_table('collection_sync_points')

