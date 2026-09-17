"""Add platform SKU profit label fee columns."""

from alembic import op
import sqlalchemy as sa


revision = "20260917_add_platform_label_fee"
down_revision = "20260909_payroll_manual_inputs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "warehouse_storage_rules",
        sa.Column("label_fee", sa.Numeric(18, 2), nullable=True),
        schema="finance",
    )
    op.add_column(
        "sku_operating_profiles",
        sa.Column("expected_label_fee", sa.Numeric(18, 2), nullable=True),
        schema="finance",
    )
    op.add_column(
        "sku_profit_estimates",
        sa.Column("expected_label_fee", sa.Numeric(18, 2), nullable=True),
        schema="finance",
    )


def downgrade() -> None:
    op.drop_column("sku_profit_estimates", "expected_label_fee", schema="finance")
    op.drop_column("sku_operating_profiles", "expected_label_fee", schema="finance")
    op.drop_column("warehouse_storage_rules", "label_fee", schema="finance")
