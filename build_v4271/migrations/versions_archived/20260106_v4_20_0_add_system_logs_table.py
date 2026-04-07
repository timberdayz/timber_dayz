"""add_system_logs_table

Revision ID: v4_20_0_system_logs
Revises: v4_19_4_rate_limit_config
Create Date: 2026-01-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'v4_20_0_system_logs'
down_revision = 'v4_19_4_rate_limit_config'
branch_labels = None
depends_on = None


def upgrade():
    # 创建系统日志表
    op.create_table(
        'system_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('level', sa.String(length=10), nullable=False),
        sa.Column('module', sa.String(length=64), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=512), nullable=True),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['dim_users.user_id'], name='fk_system_logs_user_id'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 创建索引
    op.create_index('ix_system_logs_level', 'system_logs', ['level'])
    op.create_index('ix_system_logs_module', 'system_logs', ['module'])
    op.create_index('ix_system_logs_created_at', 'system_logs', ['created_at'])


def downgrade():
    # 删除索引
    op.drop_index('ix_system_logs_created_at', table_name='system_logs')
    op.drop_index('ix_system_logs_module', table_name='system_logs')
    op.drop_index('ix_system_logs_level', table_name='system_logs')
    
    # 删除表
    op.drop_table('system_logs')
