"""Add extended target goal fields for profit and operation metrics.

Revision ID: 20260326_target_ext
Revises: 20260324_cloud_sync
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260326_target_ext"
down_revision = "20260324_cloud_sync"
branch_labels = None
depends_on = None


def _existing_columns(table_name: str, schema: str = "a_class") -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {col["name"] for col in inspector.get_columns(table_name, schema=schema)}


def _add_column_if_missing(table_name: str, column: sa.Column, schema: str = "a_class") -> None:
    if column.name not in _existing_columns(table_name, schema=schema):
        op.add_column(table_name, column, schema=schema)


def upgrade() -> None:
    _add_column_if_missing(
        "sales_targets",
        sa.Column("target_profit_amount", sa.Float(), nullable=False, server_default=sa.text("0")),
    )
    _add_column_if_missing(
        "sales_targets",
        sa.Column("achieved_profit_amount", sa.Float(), nullable=False, server_default=sa.text("0")),
    )
    _add_column_if_missing("sales_targets", sa.Column("product_id", sa.Integer(), nullable=True))
    _add_column_if_missing("sales_targets", sa.Column("platform_sku", sa.String(length=128), nullable=True))
    _add_column_if_missing("sales_targets", sa.Column("company_sku", sa.String(length=128), nullable=True))
    _add_column_if_missing("sales_targets", sa.Column("metric_code", sa.String(length=64), nullable=True))
    _add_column_if_missing("sales_targets", sa.Column("metric_name", sa.String(length=128), nullable=True))
    _add_column_if_missing("sales_targets", sa.Column("metric_direction", sa.String(length=32), nullable=True))
    _add_column_if_missing("sales_targets", sa.Column("target_value", sa.Float(), nullable=True))
    _add_column_if_missing("sales_targets", sa.Column("achieved_value", sa.Float(), nullable=True))
    _add_column_if_missing("sales_targets", sa.Column("max_score", sa.Float(), nullable=True))
    _add_column_if_missing(
        "sales_targets",
        sa.Column("penalty_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    _add_column_if_missing("sales_targets", sa.Column("penalty_threshold", sa.Float(), nullable=True))
    _add_column_if_missing("sales_targets", sa.Column("penalty_per_unit", sa.Float(), nullable=True))
    _add_column_if_missing("sales_targets", sa.Column("penalty_max", sa.Float(), nullable=True))
    _add_column_if_missing(
        "sales_targets",
        sa.Column("manual_score_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    _add_column_if_missing("sales_targets", sa.Column("manual_score_value", sa.Float(), nullable=True))

    _add_column_if_missing(
        "target_breakdown",
        sa.Column("target_profit_amount", sa.Float(), nullable=False, server_default=sa.text("0")),
    )
    _add_column_if_missing(
        "target_breakdown",
        sa.Column("achieved_profit_amount", sa.Float(), nullable=False, server_default=sa.text("0")),
    )
    _add_column_if_missing("target_breakdown", sa.Column("product_id", sa.Integer(), nullable=True))
    _add_column_if_missing("target_breakdown", sa.Column("platform_sku", sa.String(length=128), nullable=True))
    _add_column_if_missing("target_breakdown", sa.Column("company_sku", sa.String(length=128), nullable=True))
    _add_column_if_missing("target_breakdown", sa.Column("target_value", sa.Float(), nullable=True))
    _add_column_if_missing("target_breakdown", sa.Column("achieved_value", sa.Float(), nullable=True))
    _add_column_if_missing("target_breakdown", sa.Column("manual_score_value", sa.Float(), nullable=True))


def downgrade() -> None:
    existing_target_breakdown = _existing_columns("target_breakdown")
    for column_name in [
        "manual_score_value",
        "achieved_value",
        "target_value",
        "company_sku",
        "platform_sku",
        "product_id",
        "achieved_profit_amount",
        "target_profit_amount",
    ]:
        if column_name in existing_target_breakdown:
            op.drop_column("target_breakdown", column_name, schema="a_class")

    existing_sales_targets = _existing_columns("sales_targets")
    for column_name in [
        "manual_score_value",
        "manual_score_enabled",
        "penalty_max",
        "penalty_per_unit",
        "penalty_threshold",
        "penalty_enabled",
        "max_score",
        "achieved_value",
        "target_value",
        "metric_direction",
        "metric_name",
        "metric_code",
        "company_sku",
        "platform_sku",
        "product_id",
        "achieved_profit_amount",
        "target_profit_amount",
    ]:
        if column_name in existing_sales_targets:
            op.drop_column("sales_targets", column_name, schema="a_class")
