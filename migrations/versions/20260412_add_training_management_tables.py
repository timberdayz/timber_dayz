"""add training management tables

Revision ID: 20260412_training_management
Revises: 20260411_employee_tasks
Create Date: 2026-04-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260412_training_management"
down_revision = "20260411_employee_tasks"
branch_labels = None
depends_on = None

CORE_SCHEMA = "core"


def _table_names(connection, schema_name: str) -> set[str]:
    inspector = sa.inspect(connection)
    try:
        return set(inspector.get_table_names(schema=schema_name))
    except Exception:
        return set()


def _column_names(connection, table_name: str, schema_name: str) -> set[str]:
    inspector = sa.inspect(connection)
    try:
        return {column["name"] for column in inspector.get_columns(table_name, schema=schema_name)}
    except Exception:
        return set()


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {CORE_SCHEMA}"))
    table_names = _table_names(connection, CORE_SCHEMA)

    if "training_programs" not in table_names:
        op.create_table(
            "training_programs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("program_id", sa.String(length=64), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("category", sa.String(length=64), nullable=False),
            sa.Column("target_role", sa.String(length=255), nullable=False),
            sa.Column("external_platform", sa.String(length=64), nullable=False, server_default=sa.text("'飞书'")),
            sa.Column("completion_rule", sa.Text(), nullable=False),
            sa.Column("learning_url", sa.String(length=1024), nullable=True),
            sa.Column("exam_url", sa.String(length=1024), nullable=True),
            sa.Column("materials_url", sa.String(length=1024), nullable=True),
            sa.Column("external_course_id", sa.String(length=128), nullable=True),
            sa.Column("external_exam_id", sa.String(length=128), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'待上线'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("program_id", name="uq_training_programs_program_id"),
            schema=CORE_SCHEMA,
        )
        op.create_index("ix_training_programs_category", "training_programs", ["category"], unique=False, schema=CORE_SCHEMA)
        op.create_index("ix_training_programs_status", "training_programs", ["status"], unique=False, schema=CORE_SCHEMA)
    else:
        columns = _column_names(connection, "training_programs", CORE_SCHEMA)
        for column_name, column in (
            ("learning_url", sa.Column("learning_url", sa.String(length=1024), nullable=True)),
            ("exam_url", sa.Column("exam_url", sa.String(length=1024), nullable=True)),
            ("materials_url", sa.Column("materials_url", sa.String(length=1024), nullable=True)),
            ("external_course_id", sa.Column("external_course_id", sa.String(length=128), nullable=True)),
            ("external_exam_id", sa.Column("external_exam_id", sa.String(length=128), nullable=True)),
        ):
            if column_name not in columns:
                op.add_column("training_programs", column, schema=CORE_SCHEMA)

    if "training_assignments" not in table_names:
        op.create_table(
            "training_assignments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("assignment_id", sa.String(length=64), nullable=True),
            sa.Column("program_pk", sa.Integer(), nullable=False),
            sa.Column("employee_name", sa.String(length=128), nullable=False),
            sa.Column("employee_code", sa.String(length=64), nullable=False),
            sa.Column("department", sa.String(length=128), nullable=False),
            sa.Column("role_name", sa.String(length=128), nullable=False),
            sa.Column("learning_status", sa.String(length=32), nullable=False, server_default=sa.text("'待学习'")),
            sa.Column("current_status", sa.String(length=32), nullable=False, server_default=sa.text("'待学习'")),
            sa.Column("due_date", sa.String(length=32), nullable=False),
            sa.Column("supervisor_name", sa.String(length=128), nullable=False),
            sa.Column("task_id", sa.String(length=100), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["program_pk"], [f"{CORE_SCHEMA}.training_programs.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("assignment_id", name="uq_training_assignments_assignment_id"),
            schema=CORE_SCHEMA,
        )
        op.create_index("ix_training_assignments_employee_code", "training_assignments", ["employee_code"], unique=False, schema=CORE_SCHEMA)
        op.create_index("ix_training_assignments_current_status", "training_assignments", ["current_status"], unique=False, schema=CORE_SCHEMA)
        op.create_index("ix_training_assignments_program_pk", "training_assignments", ["program_pk"], unique=False, schema=CORE_SCHEMA)
        op.create_index("ix_training_assignments_task_id", "training_assignments", ["task_id"], unique=False, schema=CORE_SCHEMA)
    else:
        columns = _column_names(connection, "training_assignments", CORE_SCHEMA)
        if "task_id" not in columns:
            op.add_column("training_assignments", sa.Column("task_id", sa.String(length=100), nullable=True), schema=CORE_SCHEMA)
            op.create_index("ix_training_assignments_task_id", "training_assignments", ["task_id"], unique=False, schema=CORE_SCHEMA)

    if "training_results" not in table_names:
        op.create_table(
            "training_results",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("assignment_pk", sa.Integer(), nullable=False),
            sa.Column("exam_score", sa.Integer(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["assignment_pk"], [f"{CORE_SCHEMA}.training_assignments.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("assignment_pk", name="uq_training_results_assignment_pk"),
            schema=CORE_SCHEMA,
        )
        op.create_index("ix_training_results_assignment_pk", "training_results", ["assignment_pk"], unique=False, schema=CORE_SCHEMA)

    if "training_feishu_configs" not in table_names:
        op.create_table(
            "training_feishu_configs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("provider_code", sa.String(length=32), nullable=False, server_default=sa.text("'feishu'")),
            sa.Column("app_id", sa.String(length=128), nullable=False),
            sa.Column("app_secret_encrypted", sa.Text(), nullable=True),
            sa.Column("tenant_key", sa.String(length=128), nullable=True),
            sa.Column("base_url", sa.String(length=255), nullable=True),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("updated_by_user_id", sa.BigInteger(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["updated_by_user_id"], [f"{CORE_SCHEMA}.dim_users.user_id"]),
            sa.UniqueConstraint("provider_code", name="uq_training_feishu_configs_provider_code"),
            schema=CORE_SCHEMA,
        )


def downgrade() -> None:
    connection = op.get_bind()
    table_names = _table_names(connection, CORE_SCHEMA)

    if "training_feishu_configs" in table_names:
        op.drop_table("training_feishu_configs", schema=CORE_SCHEMA)

    if "training_results" in table_names:
        op.drop_index("ix_training_results_assignment_pk", table_name="training_results", schema=CORE_SCHEMA)
        op.drop_table("training_results", schema=CORE_SCHEMA)

    if "training_assignments" in table_names:
        if "ix_training_assignments_task_id" in {idx["name"] for idx in sa.inspect(connection).get_indexes("training_assignments", schema=CORE_SCHEMA)}:
            op.drop_index("ix_training_assignments_task_id", table_name="training_assignments", schema=CORE_SCHEMA)
        op.drop_index("ix_training_assignments_program_pk", table_name="training_assignments", schema=CORE_SCHEMA)
        op.drop_index("ix_training_assignments_current_status", table_name="training_assignments", schema=CORE_SCHEMA)
        op.drop_index("ix_training_assignments_employee_code", table_name="training_assignments", schema=CORE_SCHEMA)
        op.drop_table("training_assignments", schema=CORE_SCHEMA)

    if "training_programs" in table_names:
        op.drop_index("ix_training_programs_status", table_name="training_programs", schema=CORE_SCHEMA)
        op.drop_index("ix_training_programs_category", table_name="training_programs", schema=CORE_SCHEMA)
        op.drop_table("training_programs", schema=CORE_SCHEMA)
