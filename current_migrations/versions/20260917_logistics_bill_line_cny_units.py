"""Require a canonical CNY billing unit for every logistics bill line."""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20260917_logistics_bill_line_cny_units"
down_revision = "current_schema_20260916_sku_turnover_storage_rules_cny"
branch_labels = None
depends_on = None


_EXPECTED_UNITS = """
CASE billing_basis
    WHEN 'volume' THEN 'CNY/CBM'
    WHEN 'weight' THEN 'CNY/KG'
    WHEN 'quantity' THEN 'CNY/unit'
    WHEN 'fixed' THEN 'CNY'
    ELSE NULL
END
"""


def _has_table(table: str, schema: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table, schema=schema)


def _has_constraint(table: str, schema: str, name: str) -> bool:
    return any(
        constraint.get("name") == name
        for constraint in sa.inspect(op.get_bind()).get_check_constraints(table, schema=schema)
    )


def upgrade() -> None:
    if not _has_table("logistics_bill_lines", "finance"):
        return

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE finance.logistics_bill_lines "
            "SET billing_basis = COALESCE(billing_basis, 'volume')"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE finance.logistics_bill_lines "
            f"SET billing_unit = {_EXPECTED_UNITS} "
            "WHERE billing_unit IS NULL"
        )
    )
    invalid_count = bind.execute(
        sa.text(
            "SELECT count(*) FROM finance.logistics_bill_lines "
            f"WHERE billing_unit IS DISTINCT FROM {_EXPECTED_UNITS}"
        )
    ).scalar_one()
    if invalid_count:
        raise RuntimeError(
            "cannot enforce CNY logistics billing units: "
            f"{invalid_count} bill lines have an unsupported basis or non-CNY unit"
        )

    constraint_name = "ck_logistics_bill_lines_cny_billing_unit"
    if not _has_constraint("logistics_bill_lines", "finance", constraint_name):
        op.create_check_constraint(
            constraint_name,
            "logistics_bill_lines",
            "(billing_basis = 'volume' AND billing_unit = 'CNY/CBM') OR "
            "(billing_basis = 'weight' AND billing_unit = 'CNY/KG') OR "
            "(billing_basis = 'quantity' AND billing_unit = 'CNY/unit') OR "
            "(billing_basis = 'fixed' AND billing_unit = 'CNY')",
            schema="finance",
        )
    op.alter_column(
        "logistics_bill_lines",
        "billing_unit",
        existing_type=sa.String(length=32),
        nullable=False,
        schema="finance",
    )


def downgrade() -> None:
    raise RuntimeError("CNY logistics billing unit migration is forward-only")
