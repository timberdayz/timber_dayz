"""Add creator_commission to SKU profit estimates.

The profit preview now deducts the creator (affiliate) commission, which is a
real cash outflow. The saved profit version must record it, otherwise the
stored profit number cannot be explained from the stored cost breakdown.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "current_schema_20261021_sku_pricing_creator_commission"
down_revision = "current_schema_20261020_sku_pricing_guardrails"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str, schema: str) -> bool:
    return _inspector().has_table(table, schema=schema)


def _has_column(table: str, schema: str, name: str) -> bool:
    return _has_table(table, schema) and name in {
        column["name"] for column in _inspector().get_columns(table, schema=schema)
    }


def upgrade() -> None:
    if _has_table("sku_profit_estimates", "finance") and not _has_column(
        "sku_profit_estimates", "finance", "creator_commission"
    ):
        op.add_column(
            "sku_profit_estimates",
            sa.Column("creator_commission", sa.Numeric(18, 2), nullable=True),
            schema="finance",
        )


def downgrade() -> None:
    if _has_column("sku_profit_estimates", "finance", "creator_commission"):
        op.drop_column("sku_profit_estimates", "creator_commission", schema="finance")
