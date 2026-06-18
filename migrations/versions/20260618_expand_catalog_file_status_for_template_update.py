"""Expand catalog_files.status for template update blocking state.

Revision ID: 20260618_catalog_file_status_64
Revises: 20260615_cloud_sync_run_error_summary_text
Create Date: 2026-06-18
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260618_catalog_file_status_64"
down_revision = "20260615_cloud_sync_run_error_summary_text"
branch_labels = None
depends_on = None

CHECK_NAME = "ck_catalog_files_status"
STATUSES = (
    "pending",
    "validated",
    "ingested",
    "quarantined",
    "failed",
    "partial_success",
    "processing",
    "needs_shop",
    "source_missing",
    "template_update_required",
)


def _catalog_files_schema(connection) -> str | None:
    result = connection.execute(
        sa.text(
            """
            SELECT table_schema
            FROM information_schema.tables
            WHERE table_name = 'catalog_files'
              AND table_schema IN ('public', 'core')
            ORDER BY CASE table_schema WHEN 'public' THEN 0 ELSE 1 END
            LIMIT 1
            """
        )
    )
    return result.scalar()


def _constraint_exists(connection, schema: str) -> bool:
    result = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.table_constraints
            WHERE table_schema = :schema
              AND table_name = 'catalog_files'
              AND constraint_name = :constraint_name
              AND constraint_type = 'CHECK'
            LIMIT 1
            """
        ),
        {"schema": schema, "constraint_name": CHECK_NAME},
    )
    return result.scalar() is not None


def _qualified_table(schema: str) -> str:
    return f'"{schema}".catalog_files'


def _status_check_sql() -> str:
    allowed = ", ".join(f"'{status}'" for status in STATUSES)
    return f"status IN ({allowed})"


def upgrade() -> None:
    connection = op.get_bind()
    schema = _catalog_files_schema(connection)
    if not schema:
        return

    table_name = _qualified_table(schema)
    had_check = _constraint_exists(connection, schema)
    if had_check:
        op.execute(sa.text(f"ALTER TABLE {table_name} DROP CONSTRAINT {CHECK_NAME}"))

    op.execute(sa.text(f"ALTER TABLE {table_name} ALTER COLUMN status TYPE VARCHAR(64)"))

    op.execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET status = 'template_update_required',
                error_message = 'TEMPLATE_UPDATE_REQUIRED: template update required before ingest',
                file_metadata = jsonb_set(
                    jsonb_set(
                        COALESCE(file_metadata::jsonb, '{{}}'::jsonb),
                        '{{auto_ingest}}',
                        COALESCE(file_metadata::jsonb -> 'auto_ingest', '{{}}'::jsonb),
                        true
                    ),
                    '{{auto_ingest,last_status}}',
                    '"template_update_required"'::jsonb,
                    true
                )::json
            WHERE status IN ('processing', 'pending')
              AND (
                (
                    status = 'processing'
                    AND (
                        file_metadata::jsonb #>> '{{auto_ingest,last_status}}' = 'template_update_required'
                        OR error_message ILIKE '%TEMPLATE_UPDATE_REQUIRED%'
                        OR error_message ILIKE '%template_update_required%'
                    )
                )
                OR (
                    id IN (2901, 2902)
                    AND file_name IN (
                        'shopee_orders_weekly_20260617_165632.xls',
                        'tiktok_orders_weekly_20260617_165632.xls'
                    )
                )
              )
            """
        )
    )

    if had_check:
        op.execute(
            sa.text(
                f"ALTER TABLE {table_name} ADD CONSTRAINT {CHECK_NAME} CHECK ({_status_check_sql()})"
            )
        )


def downgrade() -> None:
    connection = op.get_bind()
    schema = _catalog_files_schema(connection)
    if not schema:
        return

    table_name = _qualified_table(schema)
    had_check = _constraint_exists(connection, schema)
    if had_check:
        op.execute(sa.text(f"ALTER TABLE {table_name} DROP CONSTRAINT {CHECK_NAME}"))

    op.execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET status = 'pending'
            WHERE status = 'template_update_required'
            """
        )
    )
    op.execute(sa.text(f"ALTER TABLE {table_name} ALTER COLUMN status TYPE VARCHAR(32)"))

    if had_check:
        allowed = ", ".join(f"'{status}'" for status in STATUSES if status != "template_update_required")
        op.execute(
            sa.text(
                f"ALTER TABLE {table_name} ADD CONSTRAINT {CHECK_NAME} CHECK (status IN ({allowed}))"
            )
        )
