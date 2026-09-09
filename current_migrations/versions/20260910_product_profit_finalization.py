"""Finalize product cost, manual logistics, and Feishu projection contracts."""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20260910_product_profit_finalization"
down_revision = "current_schema_20260909_product_cost_estimates"
branch_labels = None
depends_on = None


def _column_names(connection, table_name: str, schema: str) -> set[str]:
    inspector = sa.inspect(connection)
    if not inspector.has_table(table_name, schema=schema):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name, schema=schema)}


def _add_missing_columns(table_name: str, schema: str, columns: tuple[sa.Column, ...]) -> None:
    existing = _column_names(op.get_bind(), table_name, schema)
    for column in columns:
        if column.name not in existing:
            op.add_column(table_name, column, schema=schema)


def upgrade() -> None:
    _add_missing_columns(
        "dim_erp_sku",
        "core",
        (
            sa.Column("default_purchase_cost", sa.Float()),
            sa.Column("purchase_cost_currency", sa.String(8), nullable=False, server_default="CNY"),
            sa.Column("purchase_cost_source", sa.String(64)),
            sa.Column("purchase_cost_confidence", sa.String(16), nullable=False, server_default="low"),
            sa.Column("purchase_cost_confirmed_at", sa.DateTime(timezone=True)),
        ),
    )
    _add_missing_columns(
        "logistics_bills",
        "finance",
        (
            sa.Column("notes", sa.Text()),
            sa.Column("confirmed_at", sa.DateTime(timezone=True)),
            sa.Column("confirmed_by", sa.Integer()),
            sa.Column("voided_at", sa.DateTime(timezone=True)),
            sa.Column("voided_by", sa.Integer()),
            sa.Column("void_reason", sa.Text()),
        ),
    )
    _add_missing_columns(
        "logistics_bill_lines",
        "finance",
        (
            sa.Column("sku_id", sa.Integer(), sa.ForeignKey("core.dim_erp_sku.sku_id", ondelete="RESTRICT")),
            sa.Column("shipped_qty", sa.Numeric(18, 3)),
            sa.Column("calculated_total_weight_kg", sa.Numeric(18, 3)),
            sa.Column("calculated_total_volume_cbm", sa.Numeric(18, 6)),
            sa.Column("actual_total_weight_kg", sa.Numeric(18, 3)),
            sa.Column("actual_total_volume_cbm", sa.Numeric(18, 6)),
            sa.Column("headhaul_cost", sa.Numeric(18, 2)),
            sa.Column("handling_cost", sa.Numeric(18, 2)),
            sa.Column("last_mile_cost", sa.Numeric(18, 2)),
            sa.Column("unit_headhaul_cost", sa.Numeric(18, 6)),
            sa.Column("unit_handling_cost", sa.Numeric(18, 6)),
            sa.Column("unit_last_mile_cost", sa.Numeric(18, 6)),
            sa.Column("notes", sa.Text()),
        ),
    )
    _add_missing_columns(
        "product_cost_assumption_profiles",
        "finance",
        (sa.Column("platform_fee_rate", sa.Numeric(12, 8)),),
    )
    _add_missing_columns(
        "sku_profit_estimates",
        "finance",
        (
            sa.Column("purchase_cost_source", sa.String(64)),
            sa.Column("logistics_cost_source", sa.String(64)),
            sa.Column("storage_cost_source", sa.String(64)),
            sa.Column("assumption_profile_id", sa.Integer(), sa.ForeignKey("finance.product_cost_assumption_profiles.profile_id", ondelete="SET NULL")),
        ),
    )
    op.create_index("ix_logistics_bill_lines_sku", "logistics_bill_lines", ["sku_id"], schema="finance", if_not_exists=True)

    op.create_table(
        "feishu_projection_configs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("provider_code", sa.String(32), nullable=False, server_default="feishu"),
        sa.Column("spu_table_id", sa.String(64)),
        sa.Column("sku_table_id", sa.String(64)),
        sa.Column("initialized_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider_code", name="uq_feishu_projection_config_provider"),
        schema="ops",
    )
    op.create_table(
        "feishu_projection_tasks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("business_key", sa.String(255), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("entity_type", "business_key", "payload_hash", name="uq_feishu_projection_task_payload"),
        schema="ops",
    )
    op.create_index("ix_feishu_projection_task_status", "feishu_projection_tasks", ["status", "next_retry_at"], schema="ops")
    op.create_table(
        "feishu_projection_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("ops.feishu_projection_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="ops",
    )
    op.create_index("ix_feishu_projection_log_task", "feishu_projection_logs", ["task_id", "created_at"], schema="ops")


def downgrade() -> None:
    op.drop_index("ix_feishu_projection_log_task", table_name="feishu_projection_logs", schema="ops")
    op.drop_table("feishu_projection_logs", schema="ops")
    op.drop_index("ix_feishu_projection_task_status", table_name="feishu_projection_tasks", schema="ops")
    op.drop_table("feishu_projection_tasks", schema="ops")
    op.drop_table("feishu_projection_configs", schema="ops")
