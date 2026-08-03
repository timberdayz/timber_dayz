"""Unify active monthly performance configuration to a 100-point scope.

The formal dimensions are sales (40), profit (40), and operation (20).
Key-product columns remain for forward compatibility but are disabled.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260803_unify_monthly_performance_100_point"
down_revision = "20260803_repair_target_allocation_ratio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "performance_config",
        "sales_weight",
        schema="a_class",
        server_default=sa.text("40"),
    )
    op.alter_column(
        "performance_config",
        "profit_weight",
        schema="a_class",
        server_default=sa.text("40"),
    )
    op.alter_column(
        "performance_config",
        "key_product_weight",
        schema="a_class",
        server_default=sa.text("0"),
    )
    op.alter_column(
        "performance_config",
        "sales_max_score",
        schema="a_class",
        server_default=sa.text("40"),
    )
    op.alter_column(
        "performance_config",
        "profit_max_score",
        schema="a_class",
        server_default=sa.text("40"),
    )
    op.alter_column(
        "performance_config",
        "key_product_max_score",
        schema="a_class",
        server_default=sa.text("0"),
    )
    op.execute(
        sa.text(
            """
            UPDATE a_class.performance_config
            SET sales_weight = 40,
                profit_weight = 40,
                key_product_weight = 0,
                sales_max_score = 40,
                profit_max_score = 40,
                key_product_max_score = 0,
                updated_at = now()
            WHERE is_active = true
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE a_class.performance_config
            SET sales_weight = 30,
                profit_weight = 25,
                key_product_weight = 25,
                sales_max_score = 30,
                profit_max_score = 25,
                key_product_max_score = 25,
                updated_at = now()
            WHERE is_active = true
            """
        )
    )
    for column, value in (
        ("sales_weight", "30"),
        ("profit_weight", "25"),
        ("key_product_weight", "25"),
        ("sales_max_score", "30"),
        ("profit_max_score", "25"),
        ("key_product_max_score", "25"),
    ):
        op.alter_column(
            "performance_config",
            column,
            schema="a_class",
            server_default=sa.text(value),
        )
