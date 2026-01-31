"""add year_month to employee_shop_assignments

按月份配置归属与提成：增加 year_month(YYYY-MM)，唯一约束改为 (employee_code, platform_code, shop_id, year_month)

Revision ID: 20260131_ym
Revises: 20260131_migrate_public_tables_to_a_c_class
Create Date: 2026-01-31

"""
from alembic import op
import sqlalchemy as sa


revision = "20260131_ym"
down_revision = "20260131_esa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 增加 year_month 列（先可空）
    op.add_column(
        "employee_shop_assignments",
        sa.Column("year_month", sa.String(length=7), nullable=True),
        schema="a_class",
    )
    # 2. 已有数据回填：使用当前月份 YYYY-MM
    op.execute(
        sa.text(
            "UPDATE a_class.employee_shop_assignments SET year_month = to_char(CURRENT_DATE, 'YYYY-MM') WHERE year_month IS NULL"
        )
    )
    # 3. 改为非空
    op.alter_column(
        "employee_shop_assignments",
        "year_month",
        existing_type=sa.String(length=7),
        nullable=False,
        schema="a_class",
    )
    # 4. 删除旧唯一约束
    op.drop_constraint(
        "uq_employee_shop_assignments_a",
        "employee_shop_assignments",
        schema="a_class",
        type_="unique",
    )
    # 5. 新建唯一约束（含 year_month）
    op.create_unique_constraint(
        "uq_employee_shop_assignments_a",
        "employee_shop_assignments",
        ["employee_code", "platform_code", "shop_id", "year_month"],
        schema="a_class",
    )
    # 6. 新建 year_month 索引
    op.create_index(
        "ix_employee_shop_assignments_a_year_month",
        "employee_shop_assignments",
        ["year_month"],
        schema="a_class",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_employee_shop_assignments_a_year_month",
        table_name="employee_shop_assignments",
        schema="a_class",
    )
    op.drop_constraint(
        "uq_employee_shop_assignments_a",
        "employee_shop_assignments",
        schema="a_class",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_employee_shop_assignments_a",
        "employee_shop_assignments",
        ["employee_code", "platform_code", "shop_id"],
        schema="a_class",
    )
    op.drop_column("employee_shop_assignments", "year_month", schema="a_class")
