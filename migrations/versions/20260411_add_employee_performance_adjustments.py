"""add_employee_performance_adjustments

Revision ID: 20260411_add_employee_performance_adjustments
Revises: 20260411_monthly_profit_settlement_center
Create Date: 2026-04-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260411_add_employee_performance_adjustments"
down_revision = "20260411_monthly_profit_settlement_center"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employee_performance_adjustments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("employee_code", sa.String(length=64), nullable=False),
        sa.Column("year_month", sa.String(length=7), nullable=False),
        sa.Column("adjustment_type", sa.String(length=32), nullable=False),
        sa.Column("score_delta", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        schema="a_class",
    )
    op.create_index(
        "ix_employee_performance_adjustments_employee",
        "employee_performance_adjustments",
        ["employee_code"],
        unique=False,
        schema="a_class",
    )
    op.create_index(
        "ix_employee_performance_adjustments_month",
        "employee_performance_adjustments",
        ["year_month"],
        unique=False,
        schema="a_class",
    )
    op.create_index(
        "ix_employee_performance_adjustments_status",
        "employee_performance_adjustments",
        ["status"],
        unique=False,
        schema="a_class",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_employee_performance_adjustments_status",
        table_name="employee_performance_adjustments",
        schema="a_class",
    )
    op.drop_index(
        "ix_employee_performance_adjustments_month",
        table_name="employee_performance_adjustments",
        schema="a_class",
    )
    op.drop_index(
        "ix_employee_performance_adjustments_employee",
        table_name="employee_performance_adjustments",
        schema="a_class",
    )
    op.drop_table("employee_performance_adjustments", schema="a_class")
