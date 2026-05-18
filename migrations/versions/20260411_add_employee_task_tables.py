"""Add employee collaboration task tables.

Revision ID: 20260411_employee_tasks
Revises: 20260328_task_center_merge
Create Date: 2026-04-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260411_employee_tasks"
down_revision = "20260328_task_center_merge"
branch_labels = None
depends_on = None

CORE_SCHEMA = "core"


def _existing_tables(schema_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return set(inspector.get_table_names(schema=schema_name))


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {CORE_SCHEMA}"))
    existing_tables = _existing_tables(CORE_SCHEMA)

    if "employee_tasks" not in existing_tables:
        op.create_table(
            "employee_tasks",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("task_id", sa.String(length=100), nullable=False),
            sa.Column("task_type", sa.String(length=64), nullable=False),
            sa.Column("task_category", sa.String(length=32), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'pending'")),
            sa.Column("priority", sa.String(length=16), nullable=False, server_default=sa.text("'medium'")),
            sa.Column("owner_user_id", sa.BigInteger(), nullable=False),
            sa.Column("source_type", sa.String(length=32), nullable=False),
            sa.Column("source_module", sa.String(length=64), nullable=False),
            sa.Column("source_record_type", sa.String(length=64), nullable=True),
            sa.Column("source_record_id", sa.String(length=128), nullable=True),
            sa.Column("completion_schema", sa.JSON(), nullable=True),
            sa.Column("completion_payload", sa.JSON(), nullable=True),
            sa.Column("result_status", sa.String(length=32), nullable=True),
            sa.Column("result_comment", sa.Text(), nullable=True),
            sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.BigInteger(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["owner_user_id"], ["core.dim_users.user_id"]),
            sa.ForeignKeyConstraint(["created_by"], ["core.dim_users.user_id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("task_id", name="uq_employee_tasks_task_id"),
            sa.CheckConstraint(
                "status IN ('pending', 'in_progress', 'pending_confirmation', 'completed', 'rejected', 'closed')",
                name="chk_employee_tasks_status",
            ),
            schema=CORE_SCHEMA,
        )
        op.create_index("ix_employee_tasks_owner_status", "employee_tasks", ["owner_user_id", "status"], unique=False, schema=CORE_SCHEMA)
        op.create_index("ix_employee_tasks_due_at", "employee_tasks", ["due_at"], unique=False, schema=CORE_SCHEMA)
        op.create_index(
            "ix_employee_tasks_source",
            "employee_tasks",
            ["source_module", "source_record_type", "source_record_id"],
            unique=False,
            schema=CORE_SCHEMA,
        )
        op.create_index("ix_employee_tasks_created_at", "employee_tasks", ["created_at"], unique=False, schema=CORE_SCHEMA)

    if "employee_task_logs" not in existing_tables:
        op.create_table(
            "employee_task_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("task_pk", sa.Integer(), nullable=False),
            sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
            sa.Column("action", sa.String(length=32), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("details_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["task_pk"], [f"{CORE_SCHEMA}.employee_tasks.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["actor_user_id"], ["core.dim_users.user_id"]),
            sa.PrimaryKeyConstraint("id"),
            schema=CORE_SCHEMA,
        )
        op.create_index("ix_employee_task_logs_task_created", "employee_task_logs", ["task_pk", "created_at"], unique=False, schema=CORE_SCHEMA)

    if "employee_task_participants" not in existing_tables:
        op.create_table(
            "employee_task_participants",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("task_pk", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("participant_role", sa.String(length=16), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["task_pk"], [f"{CORE_SCHEMA}.employee_tasks.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["core.dim_users.user_id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("task_pk", "user_id", "participant_role", name="uq_employee_task_participants"),
            sa.CheckConstraint(
                "participant_role IN ('cc', 'collaborator')",
                name="chk_employee_task_participant_role",
            ),
            schema=CORE_SCHEMA,
        )
        op.create_index(
            "ix_employee_task_participants_user_role",
            "employee_task_participants",
            ["user_id", "participant_role"],
            unique=False,
            schema=CORE_SCHEMA,
        )


def downgrade() -> None:
    existing_tables = _existing_tables(CORE_SCHEMA)

    if "employee_task_participants" in existing_tables:
        op.drop_index("ix_employee_task_participants_user_role", table_name="employee_task_participants", schema=CORE_SCHEMA)
        op.drop_table("employee_task_participants", schema=CORE_SCHEMA)

    if "employee_task_logs" in existing_tables:
        op.drop_index("ix_employee_task_logs_task_created", table_name="employee_task_logs", schema=CORE_SCHEMA)
        op.drop_table("employee_task_logs", schema=CORE_SCHEMA)

    if "employee_tasks" in existing_tables:
        op.drop_index("ix_employee_tasks_created_at", table_name="employee_tasks", schema=CORE_SCHEMA)
        op.drop_index("ix_employee_tasks_source", table_name="employee_tasks", schema=CORE_SCHEMA)
        op.drop_index("ix_employee_tasks_due_at", table_name="employee_tasks", schema=CORE_SCHEMA)
        op.drop_index("ix_employee_tasks_owner_status", table_name="employee_tasks", schema=CORE_SCHEMA)
        op.drop_table("employee_tasks", schema=CORE_SCHEMA)
