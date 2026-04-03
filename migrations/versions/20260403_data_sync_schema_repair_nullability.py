"""Relax legacy NOT NULL constraints that still block current data-sync insert shapes.

This follow-up repair keeps the previous compatibility columns usable by the current ORM:
- `core.data_quarantine.source_file`
- `core.data_quarantine.catalog_file_id`
- `core.data_quarantine.platform_code`
- `core.staging_orders.file_id`
- `core.staging_orders.platform_code`
- `core.staging_product_metrics.file_id`
- `core.staging_product_metrics.platform_code`

Revision ID: 20260403_sync_nulls
Revises: 20260403_data_sync_schema_repair
Create Date: 2026-04-03
"""

from alembic import op
import sqlalchemy as sa


revision = "20260403_sync_nulls"
down_revision = "20260403_data_sync_schema_repair"
branch_labels = None
depends_on = None


def _table_exists(schema_name: str, table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names(schema=schema_name)


def _drop_not_null(schema_name: str, table_name: str, column_name: str) -> None:
    op.execute(
        sa.text(
            f'ALTER TABLE "{schema_name}"."{table_name}" '
            f'ALTER COLUMN "{column_name}" DROP NOT NULL'
        )
    )


def upgrade() -> None:
    if _table_exists("core", "data_quarantine"):
        _drop_not_null("core", "data_quarantine", "platform")
        _drop_not_null("core", "data_quarantine", "data_type")

    if _table_exists("core", "staging_orders"):
        _drop_not_null("core", "staging_orders", "platform")

    if _table_exists("core", "staging_product_metrics"):
        _drop_not_null("core", "staging_product_metrics", "platform")
        _drop_not_null("core", "staging_product_metrics", "product_sku")


def downgrade() -> None:
    # Downgrading these constraints would re-break current ORM insert shapes.
    pass
