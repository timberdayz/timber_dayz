"""Add site/shop/warehouse-specific SKU operating profiles."""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20260913_sku_operating_profiles"
down_revision = "current_schema_20260911_internal_product_category_taxonomy_v1"
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


def _has_fk(table: str, schema: str, name: str) -> bool:
    return any(item.get("name") == name for item in _inspector().get_foreign_keys(table, schema=schema))


def upgrade() -> None:
    if _has_table("feishu_projection_configs", "ops") and not _has_column("feishu_projection_configs", "ops", "site_sku_table_id"):
        op.add_column("feishu_projection_configs", sa.Column("site_sku_table_id", sa.String(64), nullable=True), schema="ops")
    if not _has_table("sku_operating_profiles", "finance"):
        op.create_table(
            "sku_operating_profiles",
            sa.Column("profile_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("sku_id", sa.Integer(), sa.ForeignKey("core.dim_erp_sku.sku_id", ondelete="RESTRICT"), nullable=False),
            sa.Column("platform_code", sa.String(32), sa.ForeignKey("core.dim_platforms.platform_code", ondelete="RESTRICT"), nullable=False),
            sa.Column("shop_id", sa.String(256), nullable=False),
            sa.Column("site_code", sa.String(64), nullable=False),
            sa.Column("site_name", sa.String(128), nullable=True),
            sa.Column("warehouse_code", sa.String(128), nullable=False),
            sa.Column("warehouse_name", sa.String(256), nullable=True),
            sa.Column("transport_type", sa.String(64), nullable=True),
            sa.Column("selling_price", sa.Numeric(18, 2), nullable=True),
            sa.Column("default_coupon_amount", sa.Numeric(18, 2), nullable=True),
            sa.Column("platform_fee_rate", sa.Numeric(12, 8), nullable=True),
            sa.Column("expected_logistics_cost", sa.Numeric(18, 6), nullable=True),
            sa.Column("expected_storage_cost", sa.Numeric(18, 6), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("effective_from", sa.Date(), nullable=False, server_default=sa.func.current_date()),
            sa.Column("effective_to", sa.Date(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("status IN ('active', 'inactive')", name="ck_sku_operating_profile_status"),
            schema="finance",
        )
    if not _has_index("sku_operating_profiles", "finance", "uq_sku_operating_profile_current"):
        op.create_index(
            "uq_sku_operating_profile_current",
            "sku_operating_profiles",
            ["sku_id", "platform_code", "shop_id", "site_code", "warehouse_code"],
            unique=True,
            schema="finance",
            postgresql_where=sa.text("effective_to IS NULL AND status = 'active'"),
        )
    if not _has_index("sku_operating_profiles", "finance", "ix_sku_operating_profile_scope"):
        op.create_index("ix_sku_operating_profile_scope", "sku_operating_profiles", ["platform_code", "shop_id", "site_code", "warehouse_code"], schema="finance")
    if not _has_index("sku_operating_profiles", "finance", "ix_sku_operating_profile_sku"):
        op.create_index("ix_sku_operating_profile_sku", "sku_operating_profiles", ["sku_id", "status"], schema="finance")

    additions = (
        ("transport_type", sa.String(64)),
        ("operating_profile_id", sa.Integer()),
        ("platform_code", sa.String(32)),
        ("shop_id", sa.String(256)),
        ("site_code", sa.String(64)),
        ("warehouse_code", sa.String(128)),
    )
    for name, column_type in additions:
        if not _has_column("sku_profit_estimates", "finance", name):
            op.add_column("sku_profit_estimates", sa.Column(name, column_type, nullable=True), schema="finance")
    if _has_table("sku_profit_estimates", "finance") and not _has_fk("sku_profit_estimates", "finance", "fk_sku_profit_estimate_operating_profile"):
        op.create_foreign_key(
            "fk_sku_profit_estimate_operating_profile",
            "sku_profit_estimates",
            "sku_operating_profiles",
            ["operating_profile_id"],
            ["profile_id"],
            source_schema="finance",
            referent_schema="finance",
            ondelete="SET NULL",
        )
    if not _has_index("sku_profit_estimates", "finance", "ix_sku_profit_estimates_operating_scope"):
        op.create_index(
            "ix_sku_profit_estimates_operating_scope",
            "sku_profit_estimates",
            ["operating_profile_id", "estimate_as_of"],
            schema="finance",
        )


def downgrade() -> None:
    if _has_index("sku_profit_estimates", "finance", "ix_sku_profit_estimates_operating_scope"):
        op.drop_index("ix_sku_profit_estimates_operating_scope", table_name="sku_profit_estimates", schema="finance")
    if _has_fk("sku_profit_estimates", "finance", "fk_sku_profit_estimate_operating_profile"):
        op.drop_constraint("fk_sku_profit_estimate_operating_profile", "sku_profit_estimates", schema="finance", type_="foreignkey")
    for name in ("warehouse_code", "site_code", "shop_id", "platform_code", "operating_profile_id", "transport_type"):
        if _has_column("sku_profit_estimates", "finance", name):
            op.drop_column("sku_profit_estimates", name, schema="finance")
    for index_name in ("ix_sku_operating_profile_sku", "ix_sku_operating_profile_scope", "uq_sku_operating_profile_current"):
        if _has_index("sku_operating_profiles", "finance", index_name):
            op.drop_index(index_name, table_name="sku_operating_profiles", schema="finance")
    if _has_table("sku_operating_profiles", "finance"):
        op.drop_table("sku_operating_profiles", schema="finance")
