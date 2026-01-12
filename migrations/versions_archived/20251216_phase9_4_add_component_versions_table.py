"""Phase 9.4: 添加组件版本管理表

Revision ID: 20251216_component_versions
Revises: 20251216_sync_points
Create Date: 2025-12-16

组件版本管理：支持版本化、A/B测试、自动切换稳定版本
预期收益：安全升级 + 快速回滚
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251216_component_versions'
down_revision = '20251216_sync_points'
branch_labels = None
depends_on = None


def upgrade():
    """创建component_versions表"""
    op.create_table(
        'component_versions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('component_name', sa.String(length=100), nullable=False, comment='组件名称（不含版本号）'),
        sa.Column('version', sa.String(length=20), nullable=False, comment='版本号: 1.0.0, 1.1.0'),
        sa.Column('file_path', sa.String(length=200), nullable=False, comment='组件文件路径（相对路径）'),
        sa.Column('is_stable', sa.Boolean(), nullable=True, comment='是否为稳定版本'),
        sa.Column('is_active', sa.Boolean(), nullable=True, comment='是否启用'),
        sa.Column('is_testing', sa.Boolean(), nullable=True, comment='是否在A/B测试中'),
        sa.Column('usage_count', sa.Integer(), nullable=True, comment='使用次数'),
        sa.Column('success_count', sa.Integer(), nullable=True, comment='成功次数'),
        sa.Column('failure_count', sa.Integer(), nullable=True, comment='失败次数'),
        sa.Column('success_rate', sa.Float(), nullable=True, comment='成功率'),
        sa.Column('test_ratio', sa.Float(), nullable=True, comment='测试流量比例'),
        sa.Column('test_start_at', sa.DateTime(), nullable=True, comment='测试开始时间'),
        sa.Column('test_end_at', sa.DateTime(), nullable=True, comment='测试结束时间'),
        sa.Column('description', sa.Text(), nullable=True, comment='版本说明'),
        sa.Column('created_by', sa.String(length=100), nullable=True, comment='创建人'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('component_name', 'version', name='uq_component_version')
    )
    
    # 创建索引
    op.create_index(
        'ix_component_versions_name',
        'component_versions',
        ['component_name']
    )
    op.create_index(
        'ix_component_versions_stable',
        'component_versions',
        ['is_stable']
    )
    op.create_index(
        'ix_component_versions_success_rate',
        'component_versions',
        ['success_rate']
    )


def downgrade():
    """删除component_versions表"""
    op.drop_index('ix_component_versions_success_rate', table_name='component_versions')
    op.drop_index('ix_component_versions_stable', table_name='component_versions')
    op.drop_index('ix_component_versions_name', table_name='component_versions')
    op.drop_table('component_versions')

