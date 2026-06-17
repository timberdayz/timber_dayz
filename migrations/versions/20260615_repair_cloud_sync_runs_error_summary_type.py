"""Repair cloud sync run error_summary column type drift.

Revision ID: 20260615_cloud_sync_run_error_summary_text
Revises: 20260609_v721_shopee_products_dates
Create Date: 2026-06-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260615_cloud_sync_run_error_summary_text"
down_revision = "20260609_v721_shopee_products_dates"
branch_labels = None
depends_on = None


def _get_column_udt(connection, table_name: str, column_name: str) -> str | None:
    result = connection.execute(
        sa.text(
            """
            SELECT udt_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
              AND column_name = :column_name
            LIMIT 1
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return result.scalar()


def upgrade() -> None:
    connection = op.get_bind()
    udt_name = _get_column_udt(connection, "cloud_b_class_sync_runs", "error_summary")
    if udt_name not in {"json", "jsonb"}:
        return

    json_typeof = "jsonb_typeof" if udt_name == "jsonb" else "json_typeof"
    op.execute(
        sa.text(
            f"""
            ALTER TABLE cloud_b_class_sync_runs
            ALTER COLUMN error_summary TYPE text
            USING CASE
                WHEN error_summary IS NULL THEN NULL
                WHEN {json_typeof}(error_summary) = 'string' THEN error_summary #>> '{{}}'
                ELSE error_summary::text
            END
            """
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    udt_name = _get_column_udt(connection, "cloud_b_class_sync_runs", "error_summary")
    if udt_name != "text":
        return

    op.execute(
        sa.text(
            """
            ALTER TABLE cloud_b_class_sync_runs
            ALTER COLUMN error_summary TYPE json
            USING to_json(error_summary)
            """
        )
    )
