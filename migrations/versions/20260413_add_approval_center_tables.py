"""Add approval center domain tables.

Revision ID: 20260413_approval_center
Revises: 20260411_employee_tasks
Create Date: 2026-04-13
"""

from alembic import op
import sqlalchemy as sa


revision = "20260413_approval_center"
down_revision = "20260411_employee_tasks"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return set(inspector.get_table_names())


def upgrade() -> None:
    existing_tables = _existing_tables()

    if "approval_templates" not in existing_tables:
        op.create_table(
            "approval_templates",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("template_code", sa.String(length=100), nullable=False),
            sa.Column("template_name", sa.String(length=255), nullable=False),
            sa.Column("business_type", sa.String(length=64), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("target_route", sa.String(length=255), nullable=True),
            sa.Column("form_schema", sa.JSON(), nullable=True),
            sa.Column("approval_mode", sa.String(length=32), nullable=False, server_default=sa.text("'single'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("template_code", name="uq_approval_templates_template_code"),
        )
        op.create_index("ix_approval_templates_business_type", "approval_templates", ["business_type"], unique=False)
        op.create_index("ix_approval_templates_enabled", "approval_templates", ["enabled"], unique=False)

    if "approval_instances" not in existing_tables:
        op.create_table(
            "approval_instances",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("approval_id", sa.String(length=100), nullable=False),
            sa.Column("template_code", sa.String(length=100), nullable=False),
            sa.Column("applicant_user_id", sa.BigInteger(), nullable=False),
            sa.Column("business_key", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'draft'")),
            sa.Column("current_step", sa.Integer(), nullable=True),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["applicant_user_id"], ["core.dim_users.user_id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("approval_id", name="uq_approval_instances_approval_id"),
        )
        op.create_index("ix_approval_instances_applicant_status", "approval_instances", ["applicant_user_id", "status"], unique=False)
        op.create_index("ix_approval_instances_template_code", "approval_instances", ["template_code"], unique=False)

    if "approval_steps" not in existing_tables:
        op.create_table(
            "approval_steps",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("approval_pk", sa.Integer(), nullable=False),
            sa.Column("step_order", sa.Integer(), nullable=False),
            sa.Column("approver_type", sa.String(length=32), nullable=False),
            sa.Column("approver_user_id", sa.BigInteger(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'pending'")),
            sa.Column("acted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["approval_pk"], ["approval_instances.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["approver_user_id"], ["core.dim_users.user_id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_approval_steps_approval_order", "approval_steps", ["approval_pk", "step_order"], unique=False)
        op.create_index("ix_approval_steps_approver_status", "approval_steps", ["approver_user_id", "status"], unique=False)

    if "approval_action_logs" not in existing_tables:
        op.create_table(
            "approval_action_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("approval_pk", sa.Integer(), nullable=False),
            sa.Column("step_pk", sa.Integer(), nullable=True),
            sa.Column("actor_user_id", sa.BigInteger(), nullable=False),
            sa.Column("action_type", sa.String(length=32), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["approval_pk"], ["approval_instances.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["step_pk"], ["approval_steps.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["actor_user_id"], ["core.dim_users.user_id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_approval_action_logs_approval_created", "approval_action_logs", ["approval_pk", "created_at"], unique=False)
        op.create_index("ix_approval_action_logs_actor_created", "approval_action_logs", ["actor_user_id", "created_at"], unique=False)


def downgrade() -> None:
    existing_tables = _existing_tables()

    if "approval_action_logs" in existing_tables:
        op.drop_index("ix_approval_action_logs_actor_created", table_name="approval_action_logs")
        op.drop_index("ix_approval_action_logs_approval_created", table_name="approval_action_logs")
        op.drop_table("approval_action_logs")

    if "approval_steps" in existing_tables:
        op.drop_index("ix_approval_steps_approver_status", table_name="approval_steps")
        op.drop_index("ix_approval_steps_approval_order", table_name="approval_steps")
        op.drop_table("approval_steps")

    if "approval_instances" in existing_tables:
        op.drop_index("ix_approval_instances_template_code", table_name="approval_instances")
        op.drop_index("ix_approval_instances_applicant_status", table_name="approval_instances")
        op.drop_table("approval_instances")

    if "approval_templates" in existing_tables:
        op.drop_index("ix_approval_templates_enabled", table_name="approval_templates")
        op.drop_index("ix_approval_templates_business_type", table_name="approval_templates")
        op.drop_table("approval_templates")
