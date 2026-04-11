"""add monthly profit settlement center tables

Revision ID: 20260411_monthly_profit_settlement_center
Revises: 20260409_field_mapping_template_timestamp_defaults
Create Date: 2026-04-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260411_monthly_profit_settlement_center"
down_revision = "20260409_field_mapping_template_timestamp_defaults"
branch_labels = None
depends_on = None

FINANCE_SCHEMA = "finance"


def _table_names(connection, schema_name: str) -> set[str]:
    inspector = sa.inspect(connection)
    try:
        return set(inspector.get_table_names(schema=schema_name))
    except Exception:
        return set()


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {FINANCE_SCHEMA}"))
    table_names = _table_names(connection, FINANCE_SCHEMA)

    if "monthly_profit_settlements" not in table_names:
        op.create_table(
            "monthly_profit_settlements",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "period_month",
                sa.String(length=16),
                sa.ForeignKey("core.dim_fiscal_calendar.period_code"),
                nullable=False,
            ),
            sa.Column("net_profit_amount", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("personnel_target_ratio", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("follow_target_ratio", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("company_target_ratio", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("personnel_target_amount", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("follow_target_amount", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("company_target_amount", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("personnel_actual_amount", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("follow_actual_amount", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("company_actual_amount", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("adjustment_amount", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("difference_amount", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("difference_ratio", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'draft'")),
            sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("approved_by", sa.String(length=64), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("remark", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.UniqueConstraint("period_month", name="uq_monthly_profit_settlements_period"),
            schema=FINANCE_SCHEMA,
        )
        op.create_index(
            "ix_monthly_profit_settlements_status",
            "monthly_profit_settlements",
            ["status"],
            unique=False,
            schema=FINANCE_SCHEMA,
        )

    if "monthly_profit_personnel_details" not in table_names:
        op.create_table(
            "monthly_profit_personnel_details",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "settlement_id",
                sa.Integer(),
                sa.ForeignKey("finance.monthly_profit_settlements.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("detail_type", sa.String(length=64), nullable=False),
            sa.Column("employee_code", sa.String(length=64), nullable=True),
            sa.Column("platform_code", sa.String(length=32), nullable=True),
            sa.Column("shop_id", sa.String(length=64), nullable=True),
            sa.Column("source_module", sa.String(length=64), nullable=True),
            sa.Column("source_record_id", sa.String(length=64), nullable=True),
            sa.Column("amount", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("remark", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            schema=FINANCE_SCHEMA,
        )
        op.create_index(
            "ix_monthly_profit_personnel_details_settlement",
            "monthly_profit_personnel_details",
            ["settlement_id"],
            unique=False,
            schema=FINANCE_SCHEMA,
        )

    if "monthly_profit_follow_details" not in table_names:
        op.create_table(
            "monthly_profit_follow_details",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "settlement_id",
                sa.Integer(),
                sa.ForeignKey("finance.monthly_profit_settlements.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "investor_user_id",
                sa.BigInteger(),
                sa.ForeignKey("core.dim_users.user_id"),
                nullable=True,
            ),
            sa.Column(
                "source_settlement_id",
                sa.Integer(),
                sa.ForeignKey("finance.follow_investment_settlements.id"),
                nullable=True,
            ),
            sa.Column("amount", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'approved'")),
            sa.Column("remark", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            schema=FINANCE_SCHEMA,
        )
        op.create_index(
            "ix_monthly_profit_follow_details_settlement",
            "monthly_profit_follow_details",
            ["settlement_id"],
            unique=False,
            schema=FINANCE_SCHEMA,
        )

    if "monthly_profit_adjustments" not in table_names:
        op.create_table(
            "monthly_profit_adjustments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "settlement_id",
                sa.Integer(),
                sa.ForeignKey("finance.monthly_profit_settlements.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("adjustment_type", sa.String(length=64), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(length=64), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            schema=FINANCE_SCHEMA,
        )
        op.create_index(
            "ix_monthly_profit_adjustments_settlement",
            "monthly_profit_adjustments",
            ["settlement_id"],
            unique=False,
            schema=FINANCE_SCHEMA,
        )


def downgrade() -> None:
    connection = op.get_bind()
    table_names = _table_names(connection, FINANCE_SCHEMA)

    if "monthly_profit_adjustments" in table_names:
        op.drop_index(
            "ix_monthly_profit_adjustments_settlement",
            table_name="monthly_profit_adjustments",
            schema=FINANCE_SCHEMA,
        )
        op.drop_table("monthly_profit_adjustments", schema=FINANCE_SCHEMA)

    if "monthly_profit_follow_details" in table_names:
        op.drop_index(
            "ix_monthly_profit_follow_details_settlement",
            table_name="monthly_profit_follow_details",
            schema=FINANCE_SCHEMA,
        )
        op.drop_table("monthly_profit_follow_details", schema=FINANCE_SCHEMA)

    if "monthly_profit_personnel_details" in table_names:
        op.drop_index(
            "ix_monthly_profit_personnel_details_settlement",
            table_name="monthly_profit_personnel_details",
            schema=FINANCE_SCHEMA,
        )
        op.drop_table("monthly_profit_personnel_details", schema=FINANCE_SCHEMA)

    if "monthly_profit_settlements" in table_names:
        op.drop_index(
            "ix_monthly_profit_settlements_status",
            table_name="monthly_profit_settlements",
            schema=FINANCE_SCHEMA,
        )
        op.drop_table("monthly_profit_settlements", schema=FINANCE_SCHEMA)
