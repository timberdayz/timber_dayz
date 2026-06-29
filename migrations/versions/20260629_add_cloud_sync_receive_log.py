"""Add cloud sync receive ledger.

Revision ID: 20260629_cloud_sync_receive_log
Revises: 20260618_catalog_shop_identity
Create Date: 2026-06-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260629_cloud_sync_receive_log"
down_revision = "20260618_catalog_shop_identity"
branch_labels = None
depends_on = None


def _table_exists(connection) -> bool:
    result = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'ops'
              AND table_name = 'cloud_sync_receive_log'
            LIMIT 1
            """
        )
    )
    return result.scalar() is not None


def upgrade() -> None:
    connection = op.get_bind()
    op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS ops"))
    if _table_exists(connection):
        return

    op.create_table(
        "cloud_sync_receive_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("receive_id", sa.String(length=100), nullable=False),
        sa.Column("source_environment", sa.String(length=64), nullable=True),
        sa.Column("checkpoint_scope", sa.String(length=64), nullable=False, server_default="b_class"),
        sa.Column("source_table_name", sa.String(length=255), nullable=False),
        sa.Column("source_file_id", sa.Integer(), nullable=True),
        sa.Column("platform_code", sa.String(length=32), nullable=True),
        sa.Column("data_domain", sa.String(length=64), nullable=True),
        sa.Column("granularity", sa.String(length=32), nullable=True),
        sa.Column("business_date_min", sa.Date(), nullable=True),
        sa.Column("business_date_max", sa.Date(), nullable=True),
        sa.Column("source_latest_ingest_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("written_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.UniqueConstraint("receive_id", name="uq_cloud_sync_receive_log_receive_id"),
        schema="ops",
    )
    op.create_index(
        "ix_cloud_sync_receive_log_created",
        "cloud_sync_receive_log",
        ["created_at"],
        schema="ops",
    )
    op.create_index(
        "ix_cloud_sync_receive_log_table_created",
        "cloud_sync_receive_log",
        ["source_table_name", "created_at"],
        schema="ops",
    )
    op.create_index(
        "ix_cloud_sync_receive_log_file",
        "cloud_sync_receive_log",
        ["source_file_id"],
        schema="ops",
    )


def downgrade() -> None:
    connection = op.get_bind()
    if _table_exists(connection):
        op.drop_index("ix_cloud_sync_receive_log_file", table_name="cloud_sync_receive_log", schema="ops")
        op.drop_index("ix_cloud_sync_receive_log_table_created", table_name="cloud_sync_receive_log", schema="ops")
        op.drop_index("ix_cloud_sync_receive_log_created", table_name="cloud_sync_receive_log", schema="ops")
        op.drop_table("cloud_sync_receive_log", schema="ops")
