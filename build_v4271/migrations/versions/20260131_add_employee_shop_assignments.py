"""add_employee_shop_assignments

add-employee-shop-assignment-page 提案: A类表员工店铺归属与提成比

Revision ID: 20260131_esa
Revises: 20260131_pub_to_ac
Create Date: 2026-01-31

"""
from alembic import op
import sqlalchemy as sa


revision = "20260131_esa"
down_revision = "20260131_pub_to_ac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employee_shop_assignments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("employee_code", sa.String(length=64), nullable=False),
        sa.Column("platform_code", sa.String(length=32), nullable=False),
        sa.Column("shop_id", sa.String(length=256), nullable=False),
        sa.Column("commission_ratio", sa.Float(), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_code", "platform_code", "shop_id", name="uq_employee_shop_assignments_a"),
        sa.ForeignKeyConstraint(
            ["platform_code", "shop_id"],
            ["dim_shops.platform_code", "dim_shops.shop_id"],
            name="fk_employee_shop_assignments_shop_a",
            ondelete="RESTRICT",
        ),
        schema="a_class",
    )
    op.create_index(
        "ix_employee_shop_assignments_a_employee",
        "employee_shop_assignments",
        ["employee_code"],
        schema="a_class",
    )
    op.create_index(
        "ix_employee_shop_assignments_a_shop",
        "employee_shop_assignments",
        ["platform_code", "shop_id"],
        schema="a_class",
    )
    op.create_index(
        "ix_employee_shop_assignments_a_status",
        "employee_shop_assignments",
        ["status"],
        schema="a_class",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_employee_shop_assignments_a_status",
        table_name="employee_shop_assignments",
        schema="a_class",
    )
    op.drop_index(
        "ix_employee_shop_assignments_a_shop",
        table_name="employee_shop_assignments",
        schema="a_class",
    )
    op.drop_index(
        "ix_employee_shop_assignments_a_employee",
        table_name="employee_shop_assignments",
        schema="a_class",
    )
    op.drop_table("employee_shop_assignments", schema="a_class")
