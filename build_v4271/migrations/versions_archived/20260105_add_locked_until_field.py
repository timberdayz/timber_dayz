"""添加账户锁定字段

Revision ID: 20260105_locked_until
Revises: 20260104_operator_role
Create Date: 2026-01-05

添加 locked_until 字段到 dim_users 表，用于账户锁定机制
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260105_locked_until'
down_revision = '20260104_operator_role'
branch_labels = None
depends_on = None


def upgrade():
    """添加 locked_until 字段"""
    # 检查字段是否已存在
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('dim_users')]
    
    if 'locked_until' not in columns:
        op.add_column(
            'dim_users',
            sa.Column('locked_until', sa.DateTime(), nullable=True, comment='账户锁定到期时间')
        )
        op.create_index('idx_users_locked_until', 'dim_users', ['locked_until'])


def downgrade():
    """移除 locked_until 字段"""
    op.drop_index('idx_users_locked_until', table_name='dim_users')
    op.drop_column('dim_users', 'locked_until')

