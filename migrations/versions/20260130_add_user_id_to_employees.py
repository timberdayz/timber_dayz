"""add user_id to a_class.employees (add-link-user-employee-management)

Revision ID: 20260130_user_id_emp
Revises: 20260130_shop_time
Create Date: 2026-01-30

说明:
- 在 a_class.employees 表增加 user_id 列（BIGINT NULL），关联 dim_users.user_id
- 应用层唯一性校验，不做跨 schema 外键
"""

from alembic import op
import sqlalchemy as sa


revision = '20260130_user_id_emp'
down_revision = '20260130_shop_time'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'employees',
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        schema='a_class'
    )
    op.create_index(
        'ix_employees_user_id',
        'employees',
        ['user_id'],
        unique=False,
        schema='a_class'
    )


def downgrade():
    op.drop_index('ix_employees_user_id', table_name='employees', schema='a_class')
    op.drop_column('employees', 'user_id', schema='a_class')
