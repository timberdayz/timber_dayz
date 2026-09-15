"""Require CNY-only logistics bill headers for product cost accounting."""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20260918_logistics_bill_currency_cny"
down_revision = "current_schema_20260917_logistics_bill_line_cny_units"
branch_labels = None
depends_on = None


def _has_table(table: str, schema: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table, schema=schema)


def _has_constraint(table: str, schema: str, name: str) -> bool:
    return any(
        constraint.get("name") == name
        for constraint in sa.inspect(op.get_bind()).get_check_constraints(table, schema=schema)
    )


def upgrade() -> None:
    if not _has_table("logistics_bills", "finance"):
        return

    bind = op.get_bind()
    foreign_currency_count = bind.execute(
        sa.text(
            "SELECT count(*) FROM finance.logistics_bills "
            "WHERE currency <> 'CNY'"
        )
    ).scalar_one()
    if foreign_currency_count:
        raise RuntimeError(
            "cannot enforce CNY logistics bill currency: "
            f"{foreign_currency_count} logistics bills have currency other than CNY"
        )

    constraint_name = "ck_logistics_bills_currency"
    if not _has_constraint("logistics_bills", "finance", constraint_name):
        op.create_check_constraint(
            constraint_name,
            "logistics_bills",
            "currency = 'CNY'",
            schema="finance",
        )


def downgrade() -> None:
    raise RuntimeError("CNY logistics bill currency migration is forward-only")
