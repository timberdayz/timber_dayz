"""Add the monthly operation-performance shop-scope snapshot."""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20260817_operation_performance_monthly_scope"
down_revision = "current_schema_20260810_operation_contract_isolation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operation_performance_shop_scopes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("year_month", sa.String(length=7), nullable=False),
        sa.Column("platform_code", sa.String(length=32), nullable=False),
        sa.Column("shop_id", sa.String(length=256), nullable=False),
        sa.Column("is_included", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("exclusion_reason", sa.String(length=512), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("updated_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["platform_code", "shop_id"],
            ["core.dim_shops.platform_code", "core.dim_shops.shop_id"],
            name="fk_operation_performance_scope_shop",
        ),
        sa.UniqueConstraint(
            "year_month",
            "platform_code",
            "shop_id",
            name="uq_operation_performance_shop_scope_month_shop",
        ),
        sa.CheckConstraint(
            "is_included OR NULLIF(btrim(exclusion_reason), '') IS NOT NULL",
            name="chk_operation_performance_scope_exclusion_reason",
        ),
        schema="a_class",
    )
    op.create_index(
        "ix_operation_performance_shop_scope_month_included",
        "operation_performance_shop_scopes",
        ["year_month", "is_included"],
        schema="a_class",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_operation_performance_shop_scope_month_included",
        table_name="operation_performance_shop_scopes",
        schema="a_class",
    )
    op.drop_table("operation_performance_shop_scopes", schema="a_class")
