"""Add label_fee columns for product-center reference costing.

Brings the current-schema chain in sync with model additions from
1fad5356 and afd9dd94 (warehouse_storage_rules.label_fee,
sku_operating_profiles.expected_label_fee,
sku_profit_estimates.expected_label_fee). The previous attempt at
20260917_add_platform_label_fee was placed in the legacy migrations/
directory and never reached production.
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20260921_warehouse_storage_label_fee"
down_revision = "current_schema_20260920_sku_direct_volume_and_profit_drafts"
branch_labels = None
depends_on = None


def _has_column(table: str, schema: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table, schema=schema) and column in {
        row["name"] for row in inspector.get_columns(table, schema=schema)
    }


def upgrade() -> None:
    if not _has_column("warehouse_storage_rules", "finance", "label_fee"):
        op.add_column(
            "warehouse_storage_rules",
            sa.Column("label_fee", sa.Numeric(18, 2), nullable=True),
            schema="finance",
        )
    if not _has_column("sku_operating_profiles", "finance", "expected_label_fee"):
        op.add_column(
            "sku_operating_profiles",
            sa.Column("expected_label_fee", sa.Numeric(18, 2), nullable=True),
            schema="finance",
        )
    if not _has_column("sku_profit_estimates", "finance", "expected_label_fee"):
        op.add_column(
            "sku_profit_estimates",
            sa.Column("expected_label_fee", sa.Numeric(18, 2), nullable=True),
            schema="finance",
        )


def downgrade() -> None:
    raise RuntimeError("label_fee migration is forward-only")
