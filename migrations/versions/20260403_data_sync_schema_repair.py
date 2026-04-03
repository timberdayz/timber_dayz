"""Repair legacy data-sync tables that were stamped to head without critical columns.

Revision ID: 20260403_data_sync_schema_repair
Revises: 20260402_main_shop_accounts
Create Date: 2026-04-03
"""

from alembic import op
import sqlalchemy as sa


revision = "20260403_data_sync_schema_repair"
down_revision = "20260402_main_shop_accounts"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _table_exists(schema_name: str, table_name: str) -> bool:
    return table_name in _inspector().get_table_names(schema=schema_name)


def _column_names(schema_name: str, table_name: str) -> set[str]:
    return {
        column["name"]
        for column in _inspector().get_columns(table_name, schema=schema_name)
    }


def _add_column_if_missing(schema_name: str, table_name: str, column_name: str, ddl: str) -> None:
    op.execute(
        sa.text(
            f'ALTER TABLE "{schema_name}"."{table_name}" '
            f'ADD COLUMN IF NOT EXISTS "{column_name}" {ddl}'
        )
    )


def _create_index_if_not_exists(
    schema_name: str,
    table_name: str,
    index_name: str,
    columns_sql: str,
) -> None:
    op.execute(
        sa.text(
            f'CREATE INDEX IF NOT EXISTS "{index_name}" '
            f'ON "{schema_name}"."{table_name}" ({columns_sql})'
        )
    )


def _repair_data_quarantine() -> None:
    schema_name = "core"
    table_name = "data_quarantine"
    if not _table_exists(schema_name, table_name):
        return

    _add_column_if_missing(schema_name, table_name, "source_file", "VARCHAR(500) NOT NULL DEFAULT ''")
    _add_column_if_missing(schema_name, table_name, "catalog_file_id", "INTEGER")
    _add_column_if_missing(schema_name, table_name, "row_number", "INTEGER")
    _add_column_if_missing(schema_name, table_name, "row_data", "TEXT NOT NULL DEFAULT '{}'")
    _add_column_if_missing(
        schema_name,
        table_name,
        "error_type",
        "VARCHAR(100) NOT NULL DEFAULT 'legacy'",
    )
    _add_column_if_missing(schema_name, table_name, "error_msg", "TEXT")
    _add_column_if_missing(schema_name, table_name, "platform_code", "VARCHAR(32)")
    _add_column_if_missing(schema_name, table_name, "shop_id", "VARCHAR(64)")
    _add_column_if_missing(schema_name, table_name, "data_domain", "VARCHAR(64)")
    _add_column_if_missing(
        schema_name,
        table_name,
        "is_resolved",
        "BOOLEAN NOT NULL DEFAULT FALSE",
    )
    _add_column_if_missing(schema_name, table_name, "resolved_at", "TIMESTAMP WITH TIME ZONE")
    _add_column_if_missing(schema_name, table_name, "resolution_note", "TEXT")

    legacy_columns = _column_names(schema_name, table_name)

    if "raw_data" in legacy_columns:
        op.execute(
            sa.text(
                """
                UPDATE core.data_quarantine
                SET row_data = raw_data::text
                WHERE raw_data IS NOT NULL
                  AND (row_data IS NULL OR row_data = '{}' OR row_data = '')
                """
            )
        )

    if "quarantine_reason" in legacy_columns:
        op.execute(
            sa.text(
                """
                UPDATE core.data_quarantine
                SET error_msg = quarantine_reason
                WHERE quarantine_reason IS NOT NULL
                  AND error_msg IS NULL
                """
            )
        )

    if "platform" in legacy_columns:
        op.execute(
            sa.text(
                """
                UPDATE core.data_quarantine
                SET platform_code = platform
                WHERE platform IS NOT NULL
                  AND platform_code IS NULL
                """
            )
        )

    if "data_type" in legacy_columns:
        op.execute(
            sa.text(
                """
                UPDATE core.data_quarantine
                SET data_domain = data_type
                WHERE data_type IS NOT NULL
                  AND data_domain IS NULL
                """
            )
        )

    _create_index_if_not_exists(schema_name, table_name, "ix_quarantine_source_file", "source_file")
    _create_index_if_not_exists(schema_name, table_name, "ix_quarantine_error_type", "error_type")
    _create_index_if_not_exists(
        schema_name,
        table_name,
        "ix_quarantine_platform_shop",
        "platform_code, shop_id",
    )
    _create_index_if_not_exists(schema_name, table_name, "ix_quarantine_created", "created_at")
    _create_index_if_not_exists(schema_name, table_name, "ix_quarantine_resolved", "is_resolved")


def _repair_staging_orders() -> None:
    schema_name = "core"
    table_name = "staging_orders"
    if not _table_exists(schema_name, table_name):
        return

    _add_column_if_missing(schema_name, table_name, "platform_code", "VARCHAR(32)")
    _add_column_if_missing(schema_name, table_name, "ingest_task_id", "VARCHAR(64)")
    _add_column_if_missing(schema_name, table_name, "file_id", "INTEGER")

    legacy_columns = _column_names(schema_name, table_name)
    if "platform" in legacy_columns:
        op.execute(
            sa.text(
                """
                UPDATE core.staging_orders
                SET platform_code = platform
                WHERE platform IS NOT NULL
                  AND platform_code IS NULL
                """
            )
        )

    _create_index_if_not_exists(schema_name, table_name, "ix_staging_orders_platform", "platform_code")
    _create_index_if_not_exists(schema_name, table_name, "ix_staging_orders_task", "ingest_task_id")
    _create_index_if_not_exists(schema_name, table_name, "ix_staging_orders_file", "file_id")


def _repair_staging_product_metrics() -> None:
    schema_name = "core"
    table_name = "staging_product_metrics"
    if not _table_exists(schema_name, table_name):
        return

    _add_column_if_missing(schema_name, table_name, "platform_code", "VARCHAR(32)")
    _add_column_if_missing(schema_name, table_name, "platform_sku", "VARCHAR(64)")
    _add_column_if_missing(schema_name, table_name, "ingest_task_id", "VARCHAR(64)")
    _add_column_if_missing(schema_name, table_name, "file_id", "INTEGER")

    legacy_columns = _column_names(schema_name, table_name)
    if "platform" in legacy_columns:
        op.execute(
            sa.text(
                """
                UPDATE core.staging_product_metrics
                SET platform_code = platform
                WHERE platform IS NOT NULL
                  AND platform_code IS NULL
                """
            )
        )

    if "product_sku" in legacy_columns:
        op.execute(
            sa.text(
                """
                UPDATE core.staging_product_metrics
                SET platform_sku = product_sku
                WHERE product_sku IS NOT NULL
                  AND platform_sku IS NULL
                """
            )
        )

    _create_index_if_not_exists(schema_name, table_name, "ix_staging_metrics_platform", "platform_code")
    _create_index_if_not_exists(schema_name, table_name, "ix_staging_metrics_task", "ingest_task_id")
    _create_index_if_not_exists(schema_name, table_name, "ix_staging_metrics_file", "file_id")


def upgrade() -> None:
    _repair_data_quarantine()
    _repair_staging_orders()
    _repair_staging_product_metrics()


def downgrade() -> None:
    # This repair migration intentionally keeps added compatibility columns in place.
    # Downgrading stamped-but-drifted databases by dropping recovered columns is unsafe.
    pass
