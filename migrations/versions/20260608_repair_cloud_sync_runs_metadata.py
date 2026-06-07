"""Repair cloud sync run metadata column for pre-existing state tables.

Revision ID: 20260608_cloud_sync_run_metadata
Revises: 20260605_collection_config_templates_batches
Create Date: 2026-06-08
"""

from alembic import op
import sqlalchemy as sa


revision = "20260608_cloud_sync_run_metadata"
down_revision = "20260605_collection_config_templates_batches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "cloud_b_class_sync_runs" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("cloud_b_class_sync_runs")}
    if "metadata_json" not in columns:
        op.add_column("cloud_b_class_sync_runs", sa.Column("metadata_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "cloud_b_class_sync_runs" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("cloud_b_class_sync_runs")}
    if "metadata_json" in columns:
        op.drop_column("cloud_b_class_sync_runs", "metadata_json")
