"""添加用户注册和审批字段到dim_users表

Revision ID: 20260104_user_registration
Revises: 20260101_shop_id
Create Date: 2026-01-04

添加用户注册和审批流程所需的字段：
- status: 用户状态 (pending/active/rejected/suspended/deleted)
- approved_at: 审批时间
- approved_by: 审批人ID
- rejection_reason: 拒绝原因
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260104_user_registration'
down_revision = '20260101_shop_id'
branch_labels = None
depends_on = None


def upgrade():
    """添加用户注册和审批字段"""
    # 添加status字段
    op.add_column(
        'dim_users',
        sa.Column(
            'status',
            sa.String(length=20),
            nullable=False,
            server_default='active',
            comment='用户状态: pending/active/rejected/suspended/deleted'
        )
    )
    
    # 添加approved_at字段
    op.add_column(
        'dim_users',
        sa.Column(
            'approved_at',
            sa.DateTime(),
            nullable=True,
            comment='审批时间'
        )
    )
    
    # 添加approved_by字段
    op.add_column(
        'dim_users',
        sa.Column(
            'approved_by',
            sa.BigInteger(),
            nullable=True,
            comment='审批人ID'
        )
    )
    
    # 添加rejection_reason字段
    op.add_column(
        'dim_users',
        sa.Column(
            'rejection_reason',
            sa.Text(),
            nullable=True,
            comment='拒绝原因'
        )
    )
    
    # 创建外键约束（自引用）
    op.create_foreign_key(
        'fk_users_approved_by',
        'dim_users', 'dim_users',
        ['approved_by'], ['user_id'],
        ondelete='SET NULL'
    )
    
    # 创建索引
    op.create_index(
        'idx_users_status',
        'dim_users',
        ['status'],
        unique=False
    )
    
    # 更新现有用户数据：设置status="active"，确保is_active=True
    op.execute("""
        UPDATE dim_users
        SET status = 'active'
        WHERE status IS NULL OR status = ''
    """)
    
    # 确保is_active与status一致
    op.execute("""
        UPDATE dim_users
        SET is_active = (status = 'active')
    """)


def downgrade():
    """移除用户注册和审批字段"""
    # 删除索引
    op.drop_index('idx_users_status', table_name='dim_users')
    
    # 删除外键约束
    op.drop_constraint('fk_users_approved_by', 'dim_users', type_='foreignkey')
    
    # 删除字段
    op.drop_column('dim_users', 'rejection_reason')
    op.drop_column('dim_users', 'approved_by')
    op.drop_column('dim_users', 'approved_at')
    op.drop_column('dim_users', 'status')

