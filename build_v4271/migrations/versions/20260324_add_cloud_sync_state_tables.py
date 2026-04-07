"""Add cloud sync state tables required by the PostgreSQL release path.

Revision ID: 20260324_cloud_sync
Revises: 20260316_tz
Create Date: 2026-03-24
"""

from alembic import op
import sqlalchemy as sa


revision = "20260324_cloud_sync"
down_revision = "20260316_tz"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return set(inspector.get_table_names())


def upgrade() -> None:
    existing_tables = _existing_tables()

    if "cloud_b_class_sync_checkpoints" not in existing_tables:
        op.create_table(
            "cloud_b_class_sync_checkpoints",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column(
                "table_schema",
                sa.String(length=64),
                nullable=False,
                server_default=sa.text("'b_class'"),
            ),
            sa.Column("table_name", sa.String(length=255), nullable=False),
            sa.Column("last_ingest_timestamp", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_source_id", sa.BigInteger(), nullable=True),
            sa.Column(
                "last_status",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'pending'"),
            ),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "table_schema",
                "table_name",
                name="uq_cloud_b_class_sync_checkpoint",
            ),
        )
        op.create_index(
            "ix_cloud_b_class_sync_checkpoint_table",
            "cloud_b_class_sync_checkpoints",
            ["table_schema", "table_name"],
            unique=False,
        )

    if "cloud_b_class_sync_runs" not in existing_tables:
        op.create_table(
            "cloud_b_class_sync_runs",
            sa.Column("run_id", sa.String(length=100), nullable=False),
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'pending'"),
            ),
            sa.Column(
                "total_tables",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "succeeded_tables",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "failed_tables",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "started_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_summary", sa.Text(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.PrimaryKeyConstraint("run_id"),
        )
        op.create_index(
            "ix_cloud_b_class_sync_runs_status",
            "cloud_b_class_sync_runs",
            ["status"],
            unique=False,
        )
        op.create_index(
            "ix_cloud_b_class_sync_runs_started_at",
            "cloud_b_class_sync_runs",
            ["started_at"],
            unique=False,
        )

    if "cloud_b_class_sync_tasks" not in existing_tables:
        op.create_table(
            "cloud_b_class_sync_tasks",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("job_id", sa.String(length=100), nullable=False),
            sa.Column("dedupe_key", sa.String(length=255), nullable=False),
            sa.Column("source_table_name", sa.String(length=255), nullable=False),
            sa.Column("platform_code", sa.String(length=32), nullable=True),
            sa.Column("data_domain", sa.String(length=64), nullable=True),
            sa.Column("sub_domain", sa.String(length=64), nullable=True),
            sa.Column("granularity", sa.String(length=32), nullable=True),
            sa.Column(
                "trigger_source",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'auto_ingest'"),
            ),
            sa.Column("source_file_id", sa.Integer(), nullable=True),
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'pending'"),
            ),
            sa.Column(
                "attempt_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("claimed_by", sa.String(length=100), nullable=True),
            sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_attempt_started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_attempt_finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("error_code", sa.String(length=64), nullable=True),
            sa.Column("projection_preset", sa.String(length=128), nullable=True),
            sa.Column("projection_status", sa.String(length=32), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("job_id"),
        )
        op.create_index(
            "ix_cloud_b_class_sync_tasks_status",
            "cloud_b_class_sync_tasks",
            ["status"],
            unique=False,
        )
        op.create_index(
            "ix_cloud_b_class_sync_tasks_source_table",
            "cloud_b_class_sync_tasks",
            ["source_table_name"],
            unique=False,
        )
        op.create_index(
            "ix_cloud_b_class_sync_tasks_dedupe_key",
            "cloud_b_class_sync_tasks",
            ["dedupe_key"],
            unique=False,
        )


def downgrade() -> None:
    existing_tables = _existing_tables()

    if "cloud_b_class_sync_tasks" in existing_tables:
        op.drop_index("ix_cloud_b_class_sync_tasks_dedupe_key", table_name="cloud_b_class_sync_tasks")
        op.drop_index("ix_cloud_b_class_sync_tasks_source_table", table_name="cloud_b_class_sync_tasks")
        op.drop_index("ix_cloud_b_class_sync_tasks_status", table_name="cloud_b_class_sync_tasks")
        op.drop_table("cloud_b_class_sync_tasks")

    if "cloud_b_class_sync_runs" in existing_tables:
        op.drop_index("ix_cloud_b_class_sync_runs_started_at", table_name="cloud_b_class_sync_runs")
        op.drop_index("ix_cloud_b_class_sync_runs_status", table_name="cloud_b_class_sync_runs")
        op.drop_table("cloud_b_class_sync_runs")

    if "cloud_b_class_sync_checkpoints" in existing_tables:
        op.drop_index(
            "ix_cloud_b_class_sync_checkpoint_table",
            table_name="cloud_b_class_sync_checkpoints",
        )
        op.drop_table("cloud_b_class_sync_checkpoints")
