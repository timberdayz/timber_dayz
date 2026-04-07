"""v4.7.0: 添加账号别名字段到platform_accounts表

Revision ID: 20251214_account_alias
Revises: 20251213_platform_accounts
Create Date: 2025-12-14

优化：添加account_alias字段，用于关联导出数据中的自定义名称（如miaoshou ERP的订单数据）
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251214_account_alias'
down_revision = '20251213_platform_accounts'
branch_labels = None
depends_on = None


def upgrade():
    """添加account_alias字段"""
    op.add_column(
        'platform_accounts',
        sa.Column(
            'account_alias',
            sa.String(length=200),
            nullable=True,
            comment='账号别名（用于关联导出数据中的自定义名称，如miaoshou ERP的订单数据）'
        )
    )


def downgrade():
    """移除account_alias字段"""
    op.drop_column('platform_accounts', 'account_alias')

