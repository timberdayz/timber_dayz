"""Add logistics bill and product profit estimate contracts."""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20260909_product_cost_estimates"
down_revision = "current_schema_20260909_product_center_master_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "logistics_bills",
        sa.Column("bill_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("bill_no", sa.String(128), nullable=False),
        sa.Column("logistics_provider", sa.String(128)),
        sa.Column("bill_date", sa.Date, nullable=False),
        sa.Column("transport_type", sa.String(64)),
        sa.Column("destination", sa.String(128)),
        sa.Column("currency", sa.String(8), nullable=False, server_default="CNY"),
        sa.Column("total_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("source_file_id", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("bill_no", name="uq_logistics_bills_bill_no"),
        schema="finance",
    )
    op.create_index("ix_logistics_bills_date_status", "logistics_bills", ["bill_date", "status"], schema="finance")
    op.create_table(
        "logistics_bill_lines",
        sa.Column("line_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("bill_id", sa.Integer, sa.ForeignKey("finance.logistics_bills.bill_id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_no", sa.Integer, nullable=False),
        sa.Column("item_code", sa.String(255)),
        sa.Column("item_description", sa.Text),
        sa.Column("packages", sa.Numeric(18, 3)),
        sa.Column("volume_cbm", sa.Numeric(18, 6)),
        sa.Column("gross_weight_kg", sa.Numeric(18, 3)),
        sa.Column("freight_unit_price", sa.Numeric(18, 6)),
        sa.Column("freight_amount", sa.Numeric(18, 2)),
        sa.Column("customs_amount", sa.Numeric(18, 2)),
        sa.Column("sensitive_amount", sa.Numeric(18, 2)),
        sa.Column("delivery_amount", sa.Numeric(18, 2)),
        sa.Column("other_amount", sa.Numeric(18, 2)),
        sa.Column("line_total_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.UniqueConstraint("bill_id", "line_no", name="uq_logistics_bill_line"),
        schema="finance",
    )
    op.create_index("ix_logistics_bill_lines_bill", "logistics_bill_lines", ["bill_id"], schema="finance")
    op.create_table(
        "logistics_bill_line_allocations",
        sa.Column("allocation_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("bill_line_id", sa.Integer, sa.ForeignKey("finance.logistics_bill_lines.line_id", ondelete="CASCADE"), nullable=False),
        sa.Column("sku_id", sa.Integer, sa.ForeignKey("core.dim_erp_sku.sku_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("allocated_quantity", sa.Numeric(18, 3)),
        sa.Column("allocation_ratio", sa.Numeric(12, 8)),
        sa.Column("allocated_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("allocation_basis", sa.String(32), nullable=False),
        sa.Column("mapping_status", sa.String(32), nullable=False, server_default="confirmed"),
        sa.UniqueConstraint("bill_line_id", "sku_id", name="uq_logistics_bill_line_sku"),
        schema="finance",
    )
    op.create_index("ix_logistics_bill_allocations_sku", "logistics_bill_line_allocations", ["sku_id"], schema="finance")
    op.create_table(
        "product_cost_assumption_profiles",
        sa.Column("profile_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("profile_name", sa.String(128), nullable=False),
        sa.Column("destination", sa.String(128)),
        sa.Column("transport_type", sa.String(64)),
        sa.Column("billing_basis", sa.String(32), nullable=False, server_default="volume"),
        sa.Column("freight_unit_rate", sa.Numeric(18, 6)),
        sa.Column("customs_rate", sa.Numeric(12, 8)),
        sa.Column("storage_unit_rate", sa.Numeric(18, 6)),
        sa.Column("return_rate", sa.Numeric(12, 8)),
        sa.Column("damage_rate", sa.Numeric(12, 8)),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date),
        sa.Column("assumption_source", sa.String(128)),
        sa.Column("confidence_level", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="finance",
    )
    op.create_index("ix_cost_assumption_scope", "product_cost_assumption_profiles", ["destination", "transport_type", "effective_from"], schema="finance")
    op.create_table(
        "sku_profit_estimates",
        sa.Column("estimate_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("sku_id", sa.Integer, sa.ForeignKey("core.dim_erp_sku.sku_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("estimate_as_of", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("assumption_version", sa.String(64), nullable=False),
        sa.Column("scenario", sa.String(32), nullable=False, server_default="base"),
        sa.Column("selling_price", sa.Numeric(18, 2)),
        sa.Column("coupon_amount", sa.Numeric(18, 2)),
        sa.Column("purchase_cost", sa.Numeric(18, 2)),
        sa.Column("logistics_cost", sa.Numeric(18, 2)),
        sa.Column("storage_cost", sa.Numeric(18, 2)),
        sa.Column("platform_fee", sa.Numeric(18, 2)),
        sa.Column("expected_return_loss", sa.Numeric(18, 2)),
        sa.Column("expected_damage_loss", sa.Numeric(18, 2)),
        sa.Column("estimated_contribution_profit", sa.Numeric(18, 2)),
        sa.Column("estimated_margin_rate", sa.Numeric(12, 8)),
        sa.Column("cost_completeness", sa.String(32), nullable=False, server_default="incomplete"),
        sa.Column("confidence_level", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("scenario IN ('base', 'conservative', 'optimistic')", name="ck_sku_profit_estimate_scenario"),
        schema="finance",
    )
    op.create_index("ix_sku_profit_estimates_sku_time", "sku_profit_estimates", ["sku_id", "estimate_as_of"], schema="finance")


def downgrade() -> None:
    op.drop_index("ix_sku_profit_estimates_sku_time", table_name="sku_profit_estimates", schema="finance")
    op.drop_table("sku_profit_estimates", schema="finance")
    op.drop_index("ix_cost_assumption_scope", table_name="product_cost_assumption_profiles", schema="finance")
    op.drop_table("product_cost_assumption_profiles", schema="finance")
    op.drop_index("ix_logistics_bill_allocations_sku", table_name="logistics_bill_line_allocations", schema="finance")
    op.drop_table("logistics_bill_line_allocations", schema="finance")
    op.drop_index("ix_logistics_bill_lines_bill", table_name="logistics_bill_lines", schema="finance")
    op.drop_table("logistics_bill_lines", schema="finance")
    op.drop_index("ix_logistics_bills_date_status", table_name="logistics_bills", schema="finance")
    op.drop_table("logistics_bills", schema="finance")
