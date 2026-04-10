"""add collection config runs

Revision ID: 20260410_collection_config_runs
Revises: 20260409_field_mapping_template_timestamp_defaults
Create Date: 2026-04-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260410_collection_config_runs"
down_revision = "20260409_field_mapping_template_timestamp_defaults"
branch_labels = None
depends_on = None

CORE_SCHEMA = "core"
RUN_TABLE = "collection_config_runs"
TASK_TABLE = "collection_tasks"
RUN_ID_COLUMN = "config_run_id"


def _table_exists(connection: sa.Connection, schema_name: str, table_name: str) -> bool:
    inspector = sa.inspect(connection)
    try:
        return table_name in set(inspector.get_table_names(schema=schema_name))
    except Exception:
        return False


def _column_exists(connection: sa.Connection, schema_name: str, table_name: str, column_name: str) -> bool:
    rows = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = :schema_name
              AND table_name = :table_name
              AND column_name = :column_name
            """
        ),
        {
            "schema_name": schema_name,
            "table_name": table_name,
            "column_name": column_name,
        },
    ).fetchall()
    return bool(rows)


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {CORE_SCHEMA}"))

    if not _table_exists(connection, CORE_SCHEMA, RUN_TABLE):
        op.create_table(
            RUN_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("run_id", sa.String(length=100), nullable=False),
            sa.Column(
                "config_id",
                sa.Integer(),
                sa.ForeignKey("core.collection_configs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("platform", sa.String(length=50), nullable=False),
            sa.Column("main_account_id", sa.String(length=100), nullable=False),
            sa.Column(
                "trigger_type",
                sa.String(length=20),
                nullable=False,
                server_default=sa.text("'scheduled'"),
            ),
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'queued'"),
            ),
            sa.Column(
                "priority",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("5"),
            ),
            sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.UniqueConstraint("run_id", name="uq_collection_config_runs_run_id"),
            schema=CORE_SCHEMA,
        )
        op.create_index(
            "ix_collection_config_runs_status",
            RUN_TABLE,
            ["status"],
            unique=False,
            schema=CORE_SCHEMA,
        )
        op.create_index(
            "ix_collection_config_runs_created_at",
            RUN_TABLE,
            ["created_at"],
            unique=False,
            schema=CORE_SCHEMA,
        )
        op.create_index(
            "ix_collection_config_runs_config_id",
            RUN_TABLE,
            ["config_id"],
            unique=False,
            schema=CORE_SCHEMA,
        )
        op.create_index(
            "ix_collection_config_runs_main_account_id",
            RUN_TABLE,
            ["main_account_id"],
            unique=False,
            schema=CORE_SCHEMA,
        )

    if _table_exists(connection, CORE_SCHEMA, TASK_TABLE) and not _column_exists(
        connection, CORE_SCHEMA, TASK_TABLE, RUN_ID_COLUMN
    ):
        op.add_column(
            TASK_TABLE,
            sa.Column(RUN_ID_COLUMN, sa.Integer(), nullable=True),
            schema=CORE_SCHEMA,
        )
        op.create_foreign_key(
            "fk_collection_tasks_config_run_id",
            TASK_TABLE,
            RUN_TABLE,
            [RUN_ID_COLUMN],
            ["id"],
            source_schema=CORE_SCHEMA,
            referent_schema=CORE_SCHEMA,
            ondelete="SET NULL",
        )
        op.create_index(
            "ix_collection_tasks_config_run",
            TASK_TABLE,
            [RUN_ID_COLUMN],
            unique=False,
            schema=CORE_SCHEMA,
        )


def downgrade() -> None:
    connection = op.get_bind()

    if _table_exists(connection, CORE_SCHEMA, TASK_TABLE) and _column_exists(
        connection, CORE_SCHEMA, TASK_TABLE, RUN_ID_COLUMN
    ):
        op.drop_index(
            "ix_collection_tasks_config_run",
            table_name=TASK_TABLE,
            schema=CORE_SCHEMA,
        )
        op.drop_constraint(
            "fk_collection_tasks_config_run_id",
            TASK_TABLE,
            schema=CORE_SCHEMA,
            type_="foreignkey",
        )
        op.drop_column(TASK_TABLE, RUN_ID_COLUMN, schema=CORE_SCHEMA)

    if _table_exists(connection, CORE_SCHEMA, RUN_TABLE):
        op.drop_index(
            "ix_collection_config_runs_main_account_id",
            table_name=RUN_TABLE,
            schema=CORE_SCHEMA,
        )
        op.drop_index(
            "ix_collection_config_runs_config_id",
            table_name=RUN_TABLE,
            schema=CORE_SCHEMA,
        )
        op.drop_index(
            "ix_collection_config_runs_created_at",
            table_name=RUN_TABLE,
            schema=CORE_SCHEMA,
        )
        op.drop_index(
            "ix_collection_config_runs_status",
            table_name=RUN_TABLE,
            schema=CORE_SCHEMA,
        )
        op.drop_table(RUN_TABLE, schema=CORE_SCHEMA)
