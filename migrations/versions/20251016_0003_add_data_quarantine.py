"""add data_quarantine table

Revision ID: 20251016_0003
Revises: 20250926_0002
Create Date: 2025-10-16 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20251016_0003"
down_revision: Union[str, None] = "20250926_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """添加data_quarantine表"""
    op.create_table(
        'data_quarantine',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        
        # 来源信息
        sa.Column('source_file', sa.String(length=500), nullable=False),
        sa.Column('catalog_file_id', sa.Integer(), nullable=True),
        sa.Column('row_number', sa.Integer(), nullable=True),
        
        # 数据内容
        sa.Column('row_data', sa.Text(), nullable=False),
        
        # 错误信息
        sa.Column('error_type', sa.String(length=100), nullable=False),
        sa.Column('error_msg', sa.Text(), nullable=True),
        
        # 元数据
        sa.Column('platform_code', sa.String(length=32), nullable=True),
        sa.Column('shop_id', sa.String(length=64), nullable=True),
        sa.Column('data_domain', sa.String(length=64), nullable=True),
        
        # 处理状态
        sa.Column('is_resolved', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolution_note', sa.Text(), nullable=True),
        
        sa.Column('created_at', sa.DateTime(), nullable=False),
        
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['catalog_file_id'], ['catalog_files.id'], ondelete='SET NULL'),
    )
    
    # 创建索引
    op.create_index('ix_quarantine_source_file', 'data_quarantine', ['source_file'])
    op.create_index('ix_quarantine_error_type', 'data_quarantine', ['error_type'])
    op.create_index('ix_quarantine_platform_shop', 'data_quarantine', ['platform_code', 'shop_id'])
    op.create_index('ix_quarantine_created', 'data_quarantine', ['created_at'])
    op.create_index('ix_quarantine_resolved', 'data_quarantine', ['is_resolved'])


def downgrade() -> None:
    """删除data_quarantine表"""
    op.drop_index('ix_quarantine_resolved', table_name='data_quarantine')
    op.drop_index('ix_quarantine_created', table_name='data_quarantine')
    op.drop_index('ix_quarantine_platform_shop', table_name='data_quarantine')
    op.drop_index('ix_quarantine_error_type', table_name='data_quarantine')
    op.drop_index('ix_quarantine_source_file', table_name='data_quarantine')
    op.drop_table('data_quarantine')

