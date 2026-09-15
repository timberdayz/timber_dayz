"""Add direct SKU volume for product-center reference costing."""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20260920_sku_direct_volume_and_profit_drafts"
down_revision = "current_schema_20260919_logistics_rule_default"
branch_labels = None
depends_on = None


def _has_column(table: str, schema: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table, schema=schema) and column in {
        row["name"] for row in inspector.get_columns(table, schema=schema)
    }


def _has_constraint(table: str, schema: str, name: str) -> bool:
    return any(
        row.get("name") == name
        for row in sa.inspect(op.get_bind()).get_check_constraints(table, schema=schema)
    )


def _has_index(table: str, schema: str, name: str) -> bool:
    return any(
        row.get("name") == name
        for row in sa.inspect(op.get_bind()).get_indexes(table, schema=schema)
    )


def upgrade() -> None:
    if not _has_column("dim_erp_sku", "core", "unit_volume_cbm"):
        op.add_column(
            "dim_erp_sku",
            sa.Column("unit_volume_cbm", sa.Numeric(18, 6), nullable=True),
            schema="core",
        )
    if not _has_constraint("dim_erp_sku", "core", "ck_dim_erp_sku_unit_volume_cbm"):
        op.create_check_constraint(
            "ck_dim_erp_sku_unit_volume_cbm",
            "dim_erp_sku",
            "unit_volume_cbm IS NULL OR unit_volume_cbm >= 0",
            schema="core",
        )
    if not _has_index("dim_erp_sku", "core", "ix_dim_erp_sku_unit_volume_cbm"):
        op.create_index(
            "ix_dim_erp_sku_unit_volume_cbm",
            "dim_erp_sku",
            ["unit_volume_cbm"],
            schema="core",
        )
    op.execute(
        sa.text(
            """
            UPDATE core.dim_erp_sku
            SET unit_volume_cbm = ROUND(
                ((package_length_cm * package_width_cm * package_height_cm) / 1000000.0)::numeric,
                6
            )
            WHERE unit_volume_cbm IS NULL
              AND package_length_cm IS NOT NULL
              AND package_width_cm IS NOT NULL
              AND package_height_cm IS NOT NULL
            """
        )
    )
    if not _has_constraint("warehouse_storage_rules", "finance", "ck_warehouse_storage_rules_window"):
        op.create_check_constraint(
            "ck_warehouse_storage_rules_window",
            "warehouse_storage_rules",
            "effective_to IS NULL OR effective_to >= effective_from",
            schema="finance",
        )


def downgrade() -> None:
    raise RuntimeError("direct SKU volume migration is forward-only")
