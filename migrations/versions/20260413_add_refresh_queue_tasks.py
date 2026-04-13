"""add refresh queue tasks

Revision ID: 20260413_refresh_queue
Revises: 20260413_approval_center, 20260413_training_feishu_integration
Create Date: 2026-04-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260413_refresh_queue"
down_revision = ("20260413_approval_center", "20260413_training_feishu_integration")
branch_labels = None
depends_on = None

CORE_SCHEMA = "core"


def _table_names(connection, schema_name: str) -> set[str]:
    inspector = sa.inspect(connection)
    try:
        return set(inspector.get_table_names(schema=schema_name))
    except Exception:
        return set()


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {CORE_SCHEMA}"))
    table_names = _table_names(connection, CORE_SCHEMA)

    if "refresh_queue_tasks" in table_names:
        return

    op.create_table(
        "refresh_queue_tasks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(length=100), nullable=False),
        sa.Column("trigger_type", sa.String(length=32), nullable=False, server_default=sa.text("'data_ingested'")),
        sa.Column("pipeline_name", sa.String(length=100), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("targets_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("job_id", name="uq_refresh_queue_tasks_job_id"),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'skipped')",
            name="chk_refresh_queue_tasks_status",
        ),
        schema=CORE_SCHEMA,
    )
    op.create_index(
        "ix_refresh_queue_tasks_status",
        "refresh_queue_tasks",
        ["status"],
        unique=False,
        schema=CORE_SCHEMA,
    )
    op.create_index(
        "ix_refresh_queue_tasks_dedupe_key",
        "refresh_queue_tasks",
        ["dedupe_key"],
        unique=False,
        schema=CORE_SCHEMA,
    )
    op.create_index(
        "ix_refresh_queue_tasks_created_at",
        "refresh_queue_tasks",
        ["created_at"],
        unique=False,
        schema=CORE_SCHEMA,
    )


def downgrade() -> None:
    connection = op.get_bind()
    table_names = _table_names(connection, CORE_SCHEMA)
    if "refresh_queue_tasks" not in table_names:
        return

    op.drop_index("ix_refresh_queue_tasks_created_at", table_name="refresh_queue_tasks", schema=CORE_SCHEMA)
    op.drop_index("ix_refresh_queue_tasks_dedupe_key", table_name="refresh_queue_tasks", schema=CORE_SCHEMA)
    op.drop_index("ix_refresh_queue_tasks_status", table_name="refresh_queue_tasks", schema=CORE_SCHEMA)
    op.drop_table("refresh_queue_tasks", schema=CORE_SCHEMA)
