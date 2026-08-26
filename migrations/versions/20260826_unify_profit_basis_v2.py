"""Persist V2 profit-basis source breakdown for audit and UI explanation.

Revision ID: 20260826_unify_profit_basis_v2
Revises: 20260808_operation_performance_workbench
"""

from alembic import op
import sqlalchemy as sa


revision = "20260826_unify_profit_basis_v2"
down_revision = "20260808_operation_performance_workbench"
branch_labels = None
depends_on = None


def _column_names(connection) -> set[str]:
    inspector = sa.inspect(connection)
    if not inspector.has_table("shop_profit_basis", schema="finance"):
        return set()
    return {column["name"] for column in inspector.get_columns("shop_profit_basis", schema="finance")}


def upgrade() -> None:
    connection = op.get_bind()
    columns = _column_names(connection)
    if not columns:
        return
    if "other_a_class_cost_amount" not in columns:
        op.add_column(
            "shop_profit_basis",
            sa.Column("other_a_class_cost_amount", sa.Float(), nullable=False, server_default="0"),
            schema="finance",
        )
    if "pre_commission_labor_cost_amount" not in columns:
        op.add_column(
            "shop_profit_basis",
            sa.Column("pre_commission_labor_cost_amount", sa.Float(), nullable=False, server_default="0"),
            schema="finance",
        )
    if "cost_status" not in columns:
        op.add_column(
            "shop_profit_basis",
            sa.Column("cost_status", sa.String(length=32), nullable=False, server_default="projected"),
            schema="finance",
        )


def downgrade() -> None:
    connection = op.get_bind()
    columns = _column_names(connection)
    for column_name in (
        "cost_status",
        "pre_commission_labor_cost_amount",
        "other_a_class_cost_amount",
    ):
        if column_name in columns:
            op.drop_column("shop_profit_basis", column_name, schema="finance")
