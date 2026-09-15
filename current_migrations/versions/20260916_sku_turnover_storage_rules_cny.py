"""Add company SKU turnover, CNY storage tariffs, and sales-platform roles."""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20260916_sku_turnover_storage_rules_cny"
down_revision = "current_schema_20260915_platform_profit_workbench"
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


def _has_index(table: str, schema: str, name: str) -> bool:
    return _has_table(table, schema) and any(
        index["name"] == name for index in _inspector().get_indexes(table, schema=schema)
    )


def _has_constraint(table: str, schema: str, name: str) -> bool:
    return _has_table(table, schema) and any(
        constraint.get("name") == name
        for constraint in _inspector().get_check_constraints(table, schema=schema)
    )


def _has_foreign_key(table: str, schema: str, name: str) -> bool:
    return _has_table(table, schema) and any(
        foreign_key.get("name") == name
        for foreign_key in _inspector().get_foreign_keys(table, schema=schema)
    )


def upgrade() -> None:
    if _has_table("dim_erp_sku", "core") and not _has_column("dim_erp_sku", "core", "turnover_class"):
        op.add_column("dim_erp_sku", sa.Column("turnover_class", sa.String(16), nullable=True), schema="core")
    if _has_table("dim_erp_sku", "core") and not _has_constraint("dim_erp_sku", "core", "ck_dim_erp_sku_turnover_class"):
        op.create_check_constraint(
            "ck_dim_erp_sku_turnover_class",
            "dim_erp_sku",
            "turnover_class IS NULL OR turnover_class IN ('fast', 'normal', 'slow')",
            schema="core",
        )

    if _has_table("dim_platforms", "core") and not _has_column("dim_platforms", "core", "platform_role"):
        op.add_column(
            "dim_platforms",
            sa.Column("platform_role", sa.String(16), nullable=False, server_default="sales"),
            schema="core",
        )
    if _has_table("dim_platforms", "core") and not _has_constraint("dim_platforms", "core", "ck_dim_platforms_role"):
        op.create_check_constraint(
            "ck_dim_platforms_role",
            "dim_platforms",
            "platform_role IN ('sales', 'source', 'test')",
            schema="core",
        )
    if _has_table("dim_platforms", "core"):
        bind = op.get_bind()
        bind.execute(sa.text("UPDATE core.dim_platforms SET platform_role = 'sales' WHERE platform_code IN ('shopee', 'tiktok', 'amazon')"))
        bind.execute(sa.text("UPDATE core.dim_platforms SET platform_role = 'source' WHERE platform_code = 'miaoshou'"))
        bind.execute(sa.text("UPDATE core.dim_platforms SET platform_role = 'test' WHERE platform_code = '验证码测试账号'"))

    if not _has_table("warehouse_storage_rules", "finance"):
        op.create_table(
            "warehouse_storage_rules",
            sa.Column("rule_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("warehouse_code", sa.String(128), nullable=False),
            sa.Column("billing_basis", sa.String(32), nullable=False, server_default="volume"),
            sa.Column("billing_unit", sa.String(32), nullable=False, server_default="CNY/CBM/month"),
            sa.Column("unit_rate_cny", sa.Numeric(18, 6), nullable=False),
            sa.Column("effective_from", sa.Date(), nullable=False),
            sa.Column("effective_to", sa.Date(), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("source", sa.String(128), nullable=True),
            sa.Column("version", sa.String(64), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(
                ["warehouse_code"],
                ["core.dim_warehouses.warehouse_code"],
                name="fk_warehouse_storage_rules_warehouse",
                ondelete="RESTRICT",
            ),
            sa.CheckConstraint("billing_basis = 'volume'", name="ck_warehouse_storage_rules_basis"),
            sa.CheckConstraint("billing_unit = 'CNY/CBM/month'", name="ck_warehouse_storage_rules_unit"),
            sa.CheckConstraint("unit_rate_cny >= 0", name="ck_warehouse_storage_rules_rate"),
            sa.CheckConstraint("status IN ('active', 'inactive')", name="ck_warehouse_storage_rules_status"),
            schema="finance",
        )
    if not _has_index("warehouse_storage_rules", "finance", "uq_warehouse_storage_rules_current"):
        op.create_index(
            "uq_warehouse_storage_rules_current",
            "warehouse_storage_rules",
            ["warehouse_code"],
            unique=True,
            schema="finance",
            postgresql_where=sa.text("status = 'active' AND effective_to IS NULL"),
        )
    if not _has_index("warehouse_storage_rules", "finance", "ix_warehouse_storage_rules_lookup"):
        op.create_index(
            "ix_warehouse_storage_rules_lookup",
            "warehouse_storage_rules",
            ["warehouse_code", "effective_from"],
            schema="finance",
        )

    if _has_table("sku_profit_estimates", "finance"):
        additions = (
            sa.Column("reference_storage_days", sa.Integer(), nullable=True),
            sa.Column("storage_rule_id", sa.Integer(), nullable=True),
            sa.Column("storage_rule_version", sa.String(64), nullable=True),
        )
        for column in additions:
            if not _has_column("sku_profit_estimates", "finance", column.name):
                op.add_column("sku_profit_estimates", column, schema="finance")
        if not _has_foreign_key("sku_profit_estimates", "finance", "fk_sku_profit_estimates_storage_rule"):
            op.create_foreign_key(
                "fk_sku_profit_estimates_storage_rule",
                "sku_profit_estimates",
                "warehouse_storage_rules",
                ["storage_rule_id"],
                ["rule_id"],
                source_schema="finance",
                referent_schema="finance",
                ondelete="SET NULL",
            )


def downgrade() -> None:
    raise RuntimeError("SKU turnover and CNY storage migration is forward-only")
