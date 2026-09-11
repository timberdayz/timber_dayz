"""Add company logistics provider rules and purchase-order batch links."""

from alembic import op
import sqlalchemy as sa

revision = "current_schema_20260911_product_center_logistics_v2"
down_revision = "current_schema_20260910_payroll_manual_inputs"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str, schema: str) -> bool:
    return _inspector().has_table(name, schema=schema)


def _add_columns(table: str, schema: str, columns: tuple[sa.Column, ...]) -> None:
    existing = {item["name"] for item in _inspector().get_columns(table, schema=schema)} if _has_table(table, schema) else set()
    for column in columns:
        if column.name not in existing:
            op.add_column(table, column, schema=schema)


def upgrade() -> None:
    _add_columns(
        "po_lines",
        "finance",
        (sa.Column("purchase_cost_source", sa.String(64)), sa.Column("purchase_cost_confirmed_at", sa.DateTime(timezone=True))),
    )
    _add_columns(
        "logistics_bill_lines",
        "finance",
        (
            sa.Column("po_id", sa.String(64)),
            sa.Column("billing_basis", sa.String(32), nullable=False, server_default="volume"),
            sa.Column("billing_unit", sa.String(32)),
            sa.Column("billing_unit_rate", sa.Numeric(18, 6)),
            sa.Column("is_sensitive", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("sensitive_surcharge", sa.Numeric(18, 2), nullable=False, server_default="0"),
        ),
    )
    if not _has_table("logistics_provider_rules", "finance"):
        op.create_table(
            "logistics_provider_rules",
            sa.Column("rule_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("logistics_provider", sa.String(128), nullable=False),
            sa.Column("destination", sa.String(128)),
            sa.Column("transport_type", sa.String(64)),
            sa.Column("cargo_class", sa.String(64)),
            sa.Column("is_sensitive", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("billing_basis", sa.String(32), nullable=False, server_default="volume"),
            sa.Column("billing_unit", sa.String(32), nullable=False, server_default="RMB/CBM"),
            sa.Column("freight_unit_rate", sa.Numeric(18, 6)),
            sa.Column("sensitive_surcharge_mode", sa.String(32), nullable=False, server_default="manual"),
            sa.Column("sensitive_surcharge_rate", sa.Numeric(18, 6)),
            sa.Column("currency", sa.String(8), nullable=False, server_default="CNY"),
            sa.Column("effective_from", sa.Date(), nullable=False),
            sa.Column("effective_to", sa.Date()),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("source", sa.String(128)),
            sa.Column("version", sa.String(64)),
            sa.Column("notes", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            schema="finance",
        )
        op.create_index("ix_logistics_provider_rules_scope", "logistics_provider_rules", ["logistics_provider", "destination", "transport_type", "effective_from"], schema="finance")
    if not _has_table("logistics_bill_purchase_orders", "finance"):
        op.create_table(
            "logistics_bill_purchase_orders",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("bill_id", sa.Integer(), sa.ForeignKey("finance.logistics_bills.bill_id", ondelete="CASCADE"), nullable=False),
            sa.Column("po_id", sa.String(64), sa.ForeignKey("finance.po_headers.po_id", ondelete="RESTRICT"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("bill_id", "po_id", name="uq_logistics_bill_purchase_order"),
            schema="finance",
        )
        op.create_index("ix_logistics_bill_po_po", "logistics_bill_purchase_orders", ["po_id"], schema="finance")


def downgrade() -> None:
    if _has_table("logistics_bill_purchase_orders", "finance"):
        op.drop_index("ix_logistics_bill_po_po", table_name="logistics_bill_purchase_orders", schema="finance")
        op.drop_table("logistics_bill_purchase_orders", schema="finance")
    if _has_table("logistics_provider_rules", "finance"):
        op.drop_index("ix_logistics_provider_rules_scope", table_name="logistics_provider_rules", schema="finance")
        op.drop_table("logistics_provider_rules", schema="finance")
