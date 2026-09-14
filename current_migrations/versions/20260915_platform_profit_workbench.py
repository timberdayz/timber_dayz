"""Add fields for platform SKU profit workbench."""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20260915_platform_profit_workbench"
down_revision = "current_schema_20260914_warehouse_platform_profit"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_column(table: str, schema: str, name: str) -> bool:
    return _inspector().has_table(table, schema=schema) and name in {item["name"] for item in _inspector().get_columns(table, schema=schema)}


def _add_columns(table: str, schema: str, columns: tuple[sa.Column, ...]) -> None:
    for column in columns:
        if not _has_column(table, schema, column.name):
            op.add_column(table, column, schema=schema)


def upgrade() -> None:
    _add_columns("dim_platforms", "core", (
        sa.Column("fee_rate_source", sa.String(128), nullable=True),
        sa.Column("fee_rate_version", sa.String(64), nullable=True),
    ))
    _add_columns("dim_erp_sku", "core", (
        sa.Column("reference_selling_price", sa.Float(), nullable=True),
        sa.Column("selling_price_currency", sa.String(8), nullable=False, server_default="CNY"),
        sa.Column("selling_price_source", sa.String(64), nullable=True),
        sa.Column("selling_price_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    ))
    _add_columns("sku_operating_profiles", "finance", (
        sa.Column("reference_selling_price", sa.Numeric(18, 2), nullable=True),
        sa.Column("competitor_price", sa.Numeric(18, 2), nullable=True),
        sa.Column("expected_selling_price", sa.Numeric(18, 2), nullable=True),
        sa.Column("seller_coupon_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("expected_ad_rate", sa.Numeric(12, 8), nullable=True),
    ))
    _add_columns("sku_profit_estimates", "finance", (
        sa.Column("calculation_basis", sa.String(32), nullable=False, server_default="estimated"),
        sa.Column("expected_selling_price", sa.Numeric(18, 2), nullable=True),
        sa.Column("competitor_price", sa.Numeric(18, 2), nullable=True),
        sa.Column("expected_ad_rate", sa.Numeric(12, 8), nullable=True),
        sa.Column("expected_ad_cost", sa.Numeric(18, 2), nullable=True),
        sa.Column("expected_logistics_cost", sa.Numeric(18, 2), nullable=True),
        sa.Column("actual_logistics_cost", sa.Numeric(18, 2), nullable=True),
        sa.Column("expected_storage_cost", sa.Numeric(18, 2), nullable=True),
        sa.Column("actual_storage_cost", sa.Numeric(18, 2), nullable=True),
        sa.Column("expected_profit", sa.Numeric(18, 2), nullable=True),
        sa.Column("expected_margin_rate", sa.Numeric(12, 8), nullable=True),
        sa.Column("actual_recost_profit", sa.Numeric(18, 2), nullable=True),
        sa.Column("actual_recost_margin_rate", sa.Numeric(12, 8), nullable=True),
        sa.Column("actual_recost_completeness", sa.String(32), nullable=True),
        sa.Column("logistics_cost_variance", sa.Numeric(18, 2), nullable=True),
        sa.Column("storage_cost_variance", sa.Numeric(18, 2), nullable=True),
        sa.Column("total_cost_variance", sa.Numeric(18, 2), nullable=True),
    ))
    names = {item.get("name") for item in _inspector().get_check_constraints("sku_profit_estimates", schema="finance")}
    if "ck_sku_profit_estimate_basis" not in names:
        op.create_check_constraint("ck_sku_profit_estimate_basis", "sku_profit_estimates", "calculation_basis IN ('estimated', 'actual_recost')", schema="finance")
    indexes = {item["name"] for item in _inspector().get_indexes("sku_profit_estimates", schema="finance")}
    if "ix_sku_profit_estimates_workbench" not in indexes:
        op.create_index("ix_sku_profit_estimates_workbench", "sku_profit_estimates", ["platform_code", "warehouse_code", "sku_id", "estimate_as_of"], schema="finance")


def downgrade() -> None:
    raise RuntimeError("platform profit workbench migration is forward-only")
