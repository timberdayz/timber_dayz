"""Persist the V2 profit-basis breakdown used by the unified runtime."""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20260827_profit_basis_v2_breakdown"
down_revision = "current_schema_20260822_operation_metric_catalog_v3"
branch_labels = None
depends_on = None


def _column_names(connection) -> set[str]:
    inspector = sa.inspect(connection)
    if not inspector.has_table("shop_profit_basis", schema="finance"):
        return set()
    return {
        column["name"]
        for column in inspector.get_columns("shop_profit_basis", schema="finance")
    }


def upgrade() -> None:
    connection = op.get_bind()
    columns = _column_names(connection)
    if not columns:
        return

    additions = (
        sa.Column(
            "other_a_class_cost_amount",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "pre_commission_labor_cost_amount",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "cost_status",
            sa.String(length=32),
            nullable=False,
            server_default="projected",
        ),
    )
    for column in additions:
        if column.name not in columns:
            op.add_column("shop_profit_basis", column, schema="finance")


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
