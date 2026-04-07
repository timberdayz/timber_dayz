"""add follow investment profit basis tables

Revision ID: 20260407_follow_investment_profit_basis
Revises: 20260403_add_main_account_name, 20260406_collection_config_main_account_scope
Create Date: 2026-04-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260407_follow_investment_profit_basis"
down_revision = ("20260403_add_main_account_name", "20260406_collection_config_main_account_scope")
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

    if "shop_profit_basis" not in table_names:
        op.create_table(
            "shop_profit_basis",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "period_month",
                sa.String(length=16),
                sa.ForeignKey("core.dim_fiscal_calendar.period_code"),
                nullable=False,
            ),
            sa.Column("platform_code", sa.String(length=32), nullable=False),
            sa.Column("shop_id", sa.String(length=64), nullable=False),
            sa.Column(
                "orders_profit_amount",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "a_class_cost_amount",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "b_class_cost_amount",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "profit_basis_amount",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "basis_version",
                sa.String(length=64),
                nullable=False,
                server_default=sa.text("'A_ONLY_V1'"),
            ),
            sa.Column(
                "is_locked",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column(
                "created_by",
                sa.String(length=64),
                nullable=True,
                server_default=sa.text("'system'"),
            ),
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
            sa.UniqueConstraint(
                "period_month",
                "platform_code",
                "shop_id",
                "basis_version",
                name="uq_shop_profit_basis",
            ),
            schema=FINANCE_SCHEMA,
        )
        op.create_index(
            "ix_shop_profit_basis_period",
            "shop_profit_basis",
            ["period_month"],
            unique=False,
            schema=FINANCE_SCHEMA,
        )
        op.create_index(
            "ix_shop_profit_basis_shop",
            "shop_profit_basis",
            ["platform_code", "shop_id"],
            unique=False,
            schema=FINANCE_SCHEMA,
        )

    if "follow_investments" not in table_names:
        op.create_table(
            "follow_investments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "investor_user_id",
                sa.BigInteger(),
                sa.ForeignKey("core.dim_users.user_id"),
                nullable=False,
            ),
            sa.Column("platform_code", sa.String(length=32), nullable=False),
            sa.Column("shop_id", sa.String(length=64), nullable=False),
            sa.Column(
                "contribution_amount",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column("contribution_date", sa.Date(), nullable=False),
            sa.Column("withdraw_date", sa.Date(), nullable=True),
            sa.Column(
                "capital_type",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'working_capital'"),
            ),
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'active'"),
            ),
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
            "ix_follow_investments_user",
            "follow_investments",
            ["investor_user_id", "status"],
            unique=False,
            schema=FINANCE_SCHEMA,
        )
        op.create_index(
            "ix_follow_investments_shop",
            "follow_investments",
            ["platform_code", "shop_id", "contribution_date"],
            unique=False,
            schema=FINANCE_SCHEMA,
        )

    if "follow_investment_settlements" not in table_names:
        op.create_table(
            "follow_investment_settlements",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "profit_basis_id",
                sa.Integer(),
                sa.ForeignKey("finance.shop_profit_basis.id"),
                nullable=False,
            ),
            sa.Column("period_month", sa.String(length=16), nullable=False),
            sa.Column("platform_code", sa.String(length=32), nullable=False),
            sa.Column("shop_id", sa.String(length=64), nullable=False),
            sa.Column(
                "profit_basis_amount",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "distribution_ratio",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "distributable_amount",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'draft'"),
            ),
            sa.Column("approved_by", sa.String(length=64), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
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
            "ix_follow_investment_settlements_period",
            "follow_investment_settlements",
            ["period_month", "status"],
            unique=False,
            schema=FINANCE_SCHEMA,
        )
        op.create_index(
            "ix_follow_investment_settlements_shop",
            "follow_investment_settlements",
            ["platform_code", "shop_id"],
            unique=False,
            schema=FINANCE_SCHEMA,
        )

    if "follow_investment_details" not in table_names:
        op.create_table(
            "follow_investment_details",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "settlement_id",
                sa.Integer(),
                sa.ForeignKey("finance.follow_investment_settlements.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "investor_user_id",
                sa.BigInteger(),
                sa.ForeignKey("core.dim_users.user_id"),
                nullable=False,
            ),
            sa.Column(
                "contribution_amount_snapshot",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "occupied_days",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "weighted_capital",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "share_ratio",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "estimated_income",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "approved_income",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "paid_income",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "payment_status",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'pending'"),
            ),
            sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
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
            "ix_follow_investment_details_settlement",
            "follow_investment_details",
            ["settlement_id"],
            unique=False,
            schema=FINANCE_SCHEMA,
        )
        op.create_index(
            "ix_follow_investment_details_user",
            "follow_investment_details",
            ["investor_user_id", "settlement_id"],
            unique=False,
            schema=FINANCE_SCHEMA,
        )


def downgrade() -> None:
    connection = op.get_bind()
    table_names = _table_names(connection, FINANCE_SCHEMA)

    if "follow_investment_details" in table_names:
        op.drop_index(
            "ix_follow_investment_details_user",
            table_name="follow_investment_details",
            schema=FINANCE_SCHEMA,
        )
        op.drop_index(
            "ix_follow_investment_details_settlement",
            table_name="follow_investment_details",
            schema=FINANCE_SCHEMA,
        )
        op.drop_table("follow_investment_details", schema=FINANCE_SCHEMA)

    if "follow_investment_settlements" in table_names:
        op.drop_index(
            "ix_follow_investment_settlements_shop",
            table_name="follow_investment_settlements",
            schema=FINANCE_SCHEMA,
        )
        op.drop_index(
            "ix_follow_investment_settlements_period",
            table_name="follow_investment_settlements",
            schema=FINANCE_SCHEMA,
        )
        op.drop_table("follow_investment_settlements", schema=FINANCE_SCHEMA)

    if "follow_investments" in table_names:
        op.drop_index(
            "ix_follow_investments_shop",
            table_name="follow_investments",
            schema=FINANCE_SCHEMA,
        )
        op.drop_index(
            "ix_follow_investments_user",
            table_name="follow_investments",
            schema=FINANCE_SCHEMA,
        )
        op.drop_table("follow_investments", schema=FINANCE_SCHEMA)

    if "shop_profit_basis" in table_names:
        op.drop_index(
            "ix_shop_profit_basis_shop",
            table_name="shop_profit_basis",
            schema=FINANCE_SCHEMA,
        )
        op.drop_index(
            "ix_shop_profit_basis_period",
            table_name="shop_profit_basis",
            schema=FINANCE_SCHEMA,
        )
        op.drop_table("shop_profit_basis", schema=FINANCE_SCHEMA)
