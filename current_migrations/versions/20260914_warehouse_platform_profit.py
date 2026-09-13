"""Use receiving warehouse as the product-profit scope.

This is a forward migration. Previous migration files remain immutable; the
live product-center tables are normalized to platform + warehouse + SKU.
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20260914_warehouse_platform_profit"
down_revision = "current_schema_20260913_sku_operating_profiles"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str, schema: str) -> bool:
    return _inspector().has_table(name, schema=schema)


def _has_column(table: str, schema: str, column: str) -> bool:
    return _has_table(table, schema) and column in {item["name"] for item in _inspector().get_columns(table, schema=schema)}


def _has_index(table: str, schema: str, name: str) -> bool:
    return any(item["name"] == name for item in _inspector().get_indexes(table, schema=schema))


def _guard_empty(table: str, schema: str) -> None:
    if not _has_table(table, schema):
        return
    count = op.get_bind().execute(sa.text(f'SELECT COUNT(*) FROM "{schema}"."{table}"')).scalar_one()
    if count:
        raise RuntimeError(f"warehouse scope migration requires empty {schema}.{table}; found {count} rows")


def upgrade() -> None:
    if not _has_table("dim_warehouses", "core"):
        op.create_table(
            "dim_warehouses",
            sa.Column("warehouse_code", sa.String(128), primary_key=True),
            sa.Column("warehouse_name", sa.String(256), nullable=False),
            sa.Column("country_code", sa.String(16), nullable=False),
            sa.Column("country_name", sa.String(64), nullable=False),
            sa.Column("region", sa.String(64)),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("source", sa.String(128)),
            sa.Column("effective_from", sa.Date(), nullable=False, server_default=sa.func.current_date()),
            sa.Column("effective_to", sa.Date()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("status IN ('active', 'inactive')", name="ck_dim_warehouses_status"),
            schema="core",
        )
        op.create_index("ix_dim_warehouses_country_status", "dim_warehouses", ["country_code", "status"], schema="core")

    if _has_table("dim_platforms", "core") and not _has_column("dim_platforms", "core", "default_fee_rate"):
        op.add_column("dim_platforms", sa.Column("default_fee_rate", sa.Float(), nullable=True), schema="core")
    if _has_table("dim_platforms", "core") and not _has_column("dim_platforms", "core", "fee_rate_effective_from"):
        op.add_column("dim_platforms", sa.Column("fee_rate_effective_from", sa.Date(), nullable=True), schema="core")

    if _has_table("feishu_projection_configs", "ops"):
        if _has_column("feishu_projection_configs", "ops", "site_sku_table_id") and not _has_column("feishu_projection_configs", "ops", "platform_sku_profit_table_id"):
            op.alter_column("feishu_projection_configs", "site_sku_table_id", new_column_name="platform_sku_profit_table_id", schema="ops")
        elif not _has_column("feishu_projection_configs", "ops", "platform_sku_profit_table_id"):
            op.add_column("feishu_projection_configs", sa.Column("platform_sku_profit_table_id", sa.String(64), nullable=True), schema="ops")

    _guard_empty("logistics_bills", "finance")
    if _has_column("logistics_bills", "finance", "destination"):
        op.drop_column("logistics_bills", "destination", schema="finance")
    if _has_table("logistics_bills", "finance"):
        constraints = {item.get("name") for item in _inspector().get_check_constraints("logistics_bills", schema="finance")}
        if "ck_logistics_bills_transport_type" not in constraints:
            op.create_check_constraint("ck_logistics_bills_transport_type", "logistics_bills", "transport_type IS NULL OR transport_type IN ('sea', 'air', 'rail')", schema="finance")

    _guard_empty("logistics_provider_rules", "finance")
    if _has_column("logistics_provider_rules", "finance", "destination"):
        if _has_index("logistics_provider_rules", "finance", "ix_logistics_provider_rules_scope"):
            op.drop_index("ix_logistics_provider_rules_scope", table_name="logistics_provider_rules", schema="finance")
        op.add_column("logistics_provider_rules", sa.Column("warehouse_code", sa.String(128), nullable=True), schema="finance")
        op.create_foreign_key("fk_logistics_provider_rules_warehouse", "logistics_provider_rules", "dim_warehouses", ["warehouse_code"], ["warehouse_code"], source_schema="finance", referent_schema="core", ondelete="RESTRICT")
        op.drop_column("logistics_provider_rules", "destination", schema="finance")
        op.create_index("ix_logistics_provider_rules_scope", "logistics_provider_rules", ["logistics_provider", "warehouse_code", "transport_type", "effective_from"], schema="finance")

    _guard_empty("logistics_bill_lines", "finance")
    if _has_table("logistics_bill_lines", "finance") and not _has_column("logistics_bill_lines", "finance", "warehouse_code"):
        op.add_column("logistics_bill_lines", sa.Column("warehouse_code", sa.String(128), nullable=True), schema="finance")
        op.create_foreign_key("fk_logistics_bill_lines_warehouse", "logistics_bill_lines", "dim_warehouses", ["warehouse_code"], ["warehouse_code"], source_schema="finance", referent_schema="core", ondelete="RESTRICT")
        op.alter_column("logistics_bill_lines", "warehouse_code", nullable=False, schema="finance")

    _guard_empty("sku_operating_profiles", "finance")
    if _has_table("sku_operating_profiles", "finance"):
        if _has_index("sku_operating_profiles", "finance", "uq_sku_operating_profile_current"):
            op.drop_index("uq_sku_operating_profile_current", table_name="sku_operating_profiles", schema="finance")
        if _has_index("sku_operating_profiles", "finance", "ix_sku_operating_profile_scope"):
            op.drop_index("ix_sku_operating_profile_scope", table_name="sku_operating_profiles", schema="finance")
        for name in ("shop_id", "site_code", "site_name"):
            if _has_column("sku_operating_profiles", "finance", name):
                op.drop_column("sku_operating_profiles", name, schema="finance")
        op.create_index("uq_sku_operating_profile_current", "sku_operating_profiles", ["sku_id", "platform_code", "warehouse_code"], unique=True, schema="finance", postgresql_where=sa.text("effective_to IS NULL AND status = 'active'"))
        op.create_index("ix_sku_operating_profile_scope", "sku_operating_profiles", ["platform_code", "warehouse_code"], schema="finance")

    _guard_empty("sku_profit_estimates", "finance")
    if _has_table("sku_profit_estimates", "finance"):
        for name in ("shop_id", "site_code"):
            if _has_column("sku_profit_estimates", "finance", name):
                op.drop_column("sku_profit_estimates", name, schema="finance")


def downgrade() -> None:
    raise RuntimeError("warehouse scope migration is intentionally forward-only")
