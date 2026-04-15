"""Repair finance timestamp defaults.

Revision ID: 20260415_finance_ts
Revises: 20260415_c_class_ts
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260415_finance_ts"
down_revision = "20260415_c_class_ts"
branch_labels = None
depends_on = None


TARGETS = {
    "fx_rates": ("created_at",),
    "po_headers": ("created_at", "updated_at"),
    "po_lines": ("created_at",),
    "grn_headers": ("created_at",),
    "grn_lines": ("created_at",),
    "inventory_ledger": ("created_at",),
    "invoice_headers": ("created_at", "updated_at"),
    "invoice_lines": ("created_at",),
    "three_way_match_log": ("created_at",),
    "fact_expenses_month": ("created_at",),
    "allocation_rules": ("created_at",),
    "fact_expenses_allocated_day_shop_sku": ("created_at",),
    "logistics_costs": ("created_at",),
    "logistics_allocation_rules": ("created_at",),
    "tax_vouchers": ("created_at",),
    "gl_accounts": ("created_at",),
    "journal_entries": ("created_at",),
    "journal_entry_lines": ("created_at",),
    "opening_balances": ("created_at",),
    "return_orders": ("created_at",),
}


def _table_exists(connection, schema_name: str, table_name: str) -> bool:
    result = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = :schema_name
              AND table_name = :table_name
            LIMIT 1
            """
        ),
        {"schema_name": schema_name, "table_name": table_name},
    )
    return result.scalar() is not None


def _column_exists(connection, schema_name: str, table_name: str, column_name: str) -> bool:
    result = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = :schema_name
              AND table_name = :table_name
              AND column_name = :column_name
            LIMIT 1
            """
        ),
        {
            "schema_name": schema_name,
            "table_name": table_name,
            "column_name": column_name,
        },
    )
    return result.scalar() is not None


def _repair_column(schema_name: str, table_name: str, column_name: str) -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE {schema_name}.{table_name}
            SET {column_name} = now()
            WHERE {column_name} IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            ALTER TABLE {schema_name}.{table_name}
            ALTER COLUMN {column_name} SET DEFAULT now()
            """
        )
    )


def _drop_default(schema_name: str, table_name: str, column_name: str) -> None:
    op.execute(
        sa.text(
            f"""
            ALTER TABLE {schema_name}.{table_name}
            ALTER COLUMN {column_name} DROP DEFAULT
            """
        )
    )


def upgrade() -> None:
    connection = op.get_bind()

    for table_name, columns in TARGETS.items():
        if not _table_exists(connection, "finance", table_name):
            continue
        for column_name in columns:
            if _column_exists(connection, "finance", table_name, column_name):
                _repair_column("finance", table_name, column_name)


def downgrade() -> None:
    connection = op.get_bind()

    for table_name, columns in TARGETS.items():
        if not _table_exists(connection, "finance", table_name):
            continue
        for column_name in columns:
            if _column_exists(connection, "finance", table_name, column_name):
                _drop_default("finance", table_name, column_name)
