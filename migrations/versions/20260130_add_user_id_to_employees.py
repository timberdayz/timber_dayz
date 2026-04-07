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


def _column_exists(connection, schema_name: str, table_name: str, column_name: str) -> bool:
    result = connection.execute(
        sa.text(
            """
            select 1
            from information_schema.columns
            where table_schema = :schema_name
              and table_name = :table_name
              and column_name = :column_name
            limit 1
            """
        ),
        {
            "schema_name": schema_name,
            "table_name": table_name,
            "column_name": column_name,
        },
    )
    return result.scalar() is not None


def _index_exists(connection, schema_name: str, index_name: str) -> bool:
    result = connection.execute(
        sa.text(
            """
            select 1
            from pg_indexes
            where schemaname = :schema_name
              and indexname = :index_name
            limit 1
            """
        ),
        {
            "schema_name": schema_name,
            "index_name": index_name,
        },
    )
    return result.scalar() is not None


def upgrade():
    connection = op.get_bind()

    if not _column_exists(connection, "a_class", "employees", "user_id"):
        op.add_column(
            'employees',
            sa.Column('user_id', sa.BigInteger(), nullable=True),
            schema='a_class'
        )

    if not _index_exists(connection, "a_class", "ix_employees_user_id"):
        op.create_index(
            'ix_employees_user_id',
            'employees',
            ['user_id'],
            unique=False,
            schema='a_class'
        )


def downgrade():
    connection = op.get_bind()

    if _index_exists(connection, "a_class", "ix_employees_user_id"):
        op.drop_index('ix_employees_user_id', table_name='employees', schema='a_class')

    if _column_exists(connection, "a_class", "employees", "user_id"):
        op.drop_column('employees', 'user_id', schema='a_class')
