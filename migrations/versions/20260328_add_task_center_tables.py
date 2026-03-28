"""Add persistent task center tables.

Revision ID: 20260328_task_center
Revises: 20260327_catalog_source
Create Date: 2026-03-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260328_task_center"
down_revision = "20260327_catalog_source"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return set(inspector.get_table_names())


def upgrade() -> None:
    existing_tables = _existing_tables()

    if "task_center_tasks" not in existing_tables:
        op.create_table(
            "task_center_tasks",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("task_id", sa.String(length=100), nullable=False),
            sa.Column("task_family", sa.String(length=32), nullable=False),
            sa.Column("task_type", sa.String(length=64), nullable=False),
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'pending'"),
            ),
            sa.Column("trigger_source", sa.String(length=32), nullable=True),
            sa.Column(
                "priority",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("5"),
            ),
            sa.Column("runner_kind", sa.String(length=32), nullable=True),
            sa.Column("external_runner_id", sa.String(length=128), nullable=True),
            sa.Column("parent_task_id", sa.Integer(), nullable=True),
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
            sa.Column("platform_code", sa.String(length=32), nullable=True),
            sa.Column("account_id", sa.String(length=100), nullable=True),
            sa.Column("source_file_id", sa.Integer(), nullable=True),
            sa.Column("source_table_name", sa.String(length=255), nullable=True),
            sa.Column("current_step", sa.String(length=255), nullable=True),
            sa.Column("current_item", sa.String(length=500), nullable=True),
            sa.Column(
                "total_items",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "processed_items",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "success_items",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "failed_items",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "skipped_items",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "total_rows",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "processed_rows",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "valid_rows",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "error_rows",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "quarantined_rows",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "progress_percent",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column("error_summary", sa.Text(), nullable=True),
            sa.Column("details_json", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["parent_task_id"], ["task_center_tasks.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("task_id", name="uq_task_center_tasks_task_id"),
            sa.CheckConstraint(
                "status IN ('pending', 'queued', 'running', 'paused', 'retry_waiting', 'partial_success', 'completed', 'failed', 'cancelled', 'interrupted')",
                name="chk_task_center_tasks_status",
            ),
        )
        op.create_index(
            "ix_task_center_tasks_family_status",
            "task_center_tasks",
            ["task_family", "status"],
            unique=False,
        )
        op.create_index(
            "ix_task_center_tasks_created",
            "task_center_tasks",
            ["created_at"],
            unique=False,
        )
        op.create_index(
            "ix_task_center_tasks_runner",
            "task_center_tasks",
            ["runner_kind", "external_runner_id"],
            unique=False,
        )
        op.create_index(
            "ix_task_center_tasks_source_file",
            "task_center_tasks",
            ["source_file_id"],
            unique=False,
        )
        op.create_index(
            "ix_task_center_tasks_source_table",
            "task_center_tasks",
            ["source_table_name"],
            unique=False,
        )

    if "task_center_logs" not in existing_tables:
        op.create_table(
            "task_center_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("task_pk", sa.Integer(), nullable=False),
            sa.Column(
                "level",
                sa.String(length=16),
                nullable=False,
                server_default=sa.text("'info'"),
            ),
            sa.Column(
                "event_type",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'progress'"),
            ),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("details_json", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(["task_pk"], ["task_center_tasks.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_task_center_logs_task",
            "task_center_logs",
            ["task_pk"],
            unique=False,
        )
        op.create_index(
            "ix_task_center_logs_created",
            "task_center_logs",
            ["created_at"],
            unique=False,
        )
        op.create_index(
            "ix_task_center_logs_level",
            "task_center_logs",
            ["level"],
            unique=False,
        )

    if "task_center_links" not in existing_tables:
        op.create_table(
            "task_center_links",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("task_pk", sa.Integer(), nullable=False),
            sa.Column("subject_type", sa.String(length=32), nullable=False),
            sa.Column("subject_id", sa.String(length=128), nullable=True),
            sa.Column("subject_key", sa.String(length=255), nullable=True),
            sa.Column("details_json", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(["task_pk"], ["task_center_tasks.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_task_center_links_task_subject",
            "task_center_links",
            ["task_pk", "subject_type"],
            unique=False,
        )
        op.create_index(
            "ix_task_center_links_subject_id",
            "task_center_links",
            ["subject_type", "subject_id"],
            unique=False,
        )
        op.create_index(
            "ix_task_center_links_subject_key",
            "task_center_links",
            ["subject_type", "subject_key"],
            unique=False,
        )


def downgrade() -> None:
    existing_tables = _existing_tables()

    if "task_center_links" in existing_tables:
        op.drop_index("ix_task_center_links_subject_key", table_name="task_center_links")
        op.drop_index("ix_task_center_links_subject_id", table_name="task_center_links")
        op.drop_index("ix_task_center_links_task_subject", table_name="task_center_links")
        op.drop_table("task_center_links")

    if "task_center_logs" in existing_tables:
        op.drop_index("ix_task_center_logs_level", table_name="task_center_logs")
        op.drop_index("ix_task_center_logs_created", table_name="task_center_logs")
        op.drop_index("ix_task_center_logs_task", table_name="task_center_logs")
        op.drop_table("task_center_logs")

    if "task_center_tasks" in existing_tables:
        op.drop_index("ix_task_center_tasks_source_table", table_name="task_center_tasks")
        op.drop_index("ix_task_center_tasks_source_file", table_name="task_center_tasks")
        op.drop_index("ix_task_center_tasks_runner", table_name="task_center_tasks")
        op.drop_index("ix_task_center_tasks_created", table_name="task_center_tasks")
        op.drop_index("ix_task_center_tasks_family_status", table_name="task_center_tasks")
        op.drop_table("task_center_tasks")
