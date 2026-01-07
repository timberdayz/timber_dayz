"""创建user_approval_logs表

Revision ID: 20260104_user_approval_logs
Revises: 20260104_user_registration
Create Date: 2026-01-04

创建用户审批记录表，用于审计追踪
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260104_user_approval_logs'
down_revision = '20260104_user_registration'
branch_labels = None
depends_on = None


def upgrade():
    """创建user_approval_logs表"""
    op.create_table(
        'user_approval_logs',
        sa.Column('log_id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('user_id', sa.BigInteger(), nullable=False, comment='用户ID'),
        sa.Column('action', sa.String(length=20), nullable=False, comment='操作类型: approve/reject/suspend'),
        sa.Column('approved_by', sa.BigInteger(), nullable=False, comment='操作人ID'),
        sa.Column('reason', sa.Text(), nullable=True, comment='操作原因/备注'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['approved_by'], ['dim_users.user_id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['dim_users.user_id'], ),
        sa.PrimaryKeyConstraint('log_id')
    )
    
    # 创建索引
    op.create_index('idx_approval_user_time', 'user_approval_logs', ['user_id', 'created_at'], unique=False)
    op.create_index('idx_approval_action_time', 'user_approval_logs', ['action', 'created_at'], unique=False)
    op.create_index(op.f('ix_user_approval_logs_user_id'), 'user_approval_logs', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_approval_logs_action'), 'user_approval_logs', ['action'], unique=False)
    op.create_index(op.f('ix_user_approval_logs_created_at'), 'user_approval_logs', ['created_at'], unique=False)


def downgrade():
    """删除user_approval_logs表"""
    op.drop_index(op.f('ix_user_approval_logs_created_at'), table_name='user_approval_logs')
    op.drop_index(op.f('ix_user_approval_logs_action'), table_name='user_approval_logs')
    op.drop_index(op.f('ix_user_approval_logs_user_id'), table_name='user_approval_logs')
    op.drop_index('idx_approval_action_time', table_name='user_approval_logs')
    op.drop_index('idx_approval_user_time', table_name='user_approval_logs')
    op.drop_table('user_approval_logs')

