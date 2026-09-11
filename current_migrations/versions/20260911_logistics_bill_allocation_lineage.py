"""Preserve purchase-order lineage for multi-SKU logistics statement rows."""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20260911_logistics_bill_allocation_lineage"
down_revision = "current_schema_20260911_product_center_logistics_v2"
branch_labels = None
depends_on = None


def _has_column(table: str, schema: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table, schema=schema) and column in {
        item["name"] for item in inspector.get_columns(table, schema=schema)
    }


def upgrade() -> None:
    if not _has_column("logistics_bill_line_allocations", "finance", "po_id"):
        op.add_column(
            "logistics_bill_line_allocations",
            sa.Column(
                "po_id",
                sa.String(64),
                sa.ForeignKey("finance.po_headers.po_id", ondelete="RESTRICT"),
                nullable=True,
            ),
            schema="finance",
        )
        op.create_index(
            "ix_logistics_bill_allocations_po",
            "logistics_bill_line_allocations",
            ["po_id"],
            schema="finance",
        )


def downgrade() -> None:
    if _has_column("logistics_bill_line_allocations", "finance", "po_id"):
        op.drop_index(
            "ix_logistics_bill_allocations_po",
            table_name="logistics_bill_line_allocations",
            schema="finance",
        )
        op.drop_column("logistics_bill_line_allocations", "po_id", schema="finance")
