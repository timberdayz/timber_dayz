"""Add settlement-profit targets without reinterpreting legacy gross-profit targets."""

from alembic import op
import sqlalchemy as sa


revision = "20260803_settlement_profit_target"
down_revision = "20260803_unify_monthly_performance_100_point"
branch_labels = None
depends_on = None


def _existing_columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name, schema="a_class")}


def upgrade() -> None:
    for table_name in ("sales_targets", "target_breakdown"):
        if "target_profit_basis_amount" not in _existing_columns(table_name):
            op.add_column(
                table_name,
                sa.Column(
                    "target_profit_basis_amount",
                    sa.Float(),
                    nullable=False,
                    server_default=sa.text("0"),
                ),
                schema="a_class",
            )

    op.alter_column(
        "performance_scores",
        "performance_coefficient",
        schema="c_class",
        existing_type=sa.Float(),
        nullable=True,
        server_default=None,
    )


def downgrade() -> None:
    op.alter_column(
        "performance_scores",
        "performance_coefficient",
        schema="c_class",
        existing_type=sa.Float(),
        nullable=False,
        server_default=sa.text("1.0"),
    )

    for table_name in ("target_breakdown", "sales_targets"):
        if "target_profit_basis_amount" in _existing_columns(table_name):
            op.drop_column(table_name, "target_profit_basis_amount", schema="a_class")
