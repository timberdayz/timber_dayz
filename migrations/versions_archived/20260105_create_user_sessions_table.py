"""创建用户会话表

Revision ID: 20260105_user_sessions
Revises: 20260105_locked_until
Create Date: 2026-01-05

创建 user_sessions 表，用于会话管理
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260105_user_sessions'
down_revision = '20260105_locked_until'
branch_labels = None
depends_on = None


def upgrade():
    """创建 user_sessions 表"""
    op.create_table(
        'user_sessions',
        sa.Column('session_id', sa.String(64), primary_key=True, nullable=False, comment='会话ID（Token的哈希值）'),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('dim_users.user_id'), nullable=False),
        sa.Column('device_info', sa.String(255), nullable=True, comment='设备信息（User-Agent）'),
        sa.Column('ip_address', sa.String(45), nullable=True, comment='IP地址'),
        sa.Column('location', sa.String(100), nullable=True, comment='登录位置（可选）'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False, comment='创建时间（登录时间）'),
        sa.Column('expires_at', sa.DateTime(), nullable=False, comment='过期时间'),
        sa.Column('last_active_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False, comment='最后活跃时间'),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False, comment='是否有效'),
        sa.Column('revoked_at', sa.DateTime(), nullable=True, comment='撤销时间'),
        sa.Column('revoked_reason', sa.String(100), nullable=True, comment='撤销原因'),
    )
    
    # 创建索引
    op.create_index('idx_session_user_active', 'user_sessions', ['user_id', 'is_active'])
    op.create_index('idx_session_expires', 'user_sessions', ['expires_at'])
    op.create_index('idx_sessions_user_id', 'user_sessions', ['user_id'])


def downgrade():
    """删除 user_sessions 表"""
    op.drop_index('idx_sessions_user_id', table_name='user_sessions')
    op.drop_index('idx_session_expires', table_name='user_sessions')
    op.drop_index('idx_session_user_active', table_name='user_sessions')
    op.drop_table('user_sessions')

