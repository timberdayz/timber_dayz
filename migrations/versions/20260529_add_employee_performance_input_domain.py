"""add employee performance input domain

Revision ID: 20260529_add_employee_performance_input_domain
Revises: 20260529_add_salary_structure_performance_package
Create Date: 2026-05-29
"""

from alembic import op
import sqlalchemy as sa


revision = "20260529_add_employee_performance_input_domain"
down_revision = "20260529_add_salary_structure_performance_package"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employee_performance_inputs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("employee_code", sa.String(length=64), nullable=False),
        sa.Column("year_month", sa.String(length=7), nullable=False),
        sa.Column("metric_code", sa.String(length=64), nullable=False),
        sa.Column("metric_name", sa.String(length=128), nullable=True),
        sa.Column("metric_direction", sa.String(length=32), nullable=False),
        sa.Column("target_value", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("achieved_value", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_score", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("manual_score_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("manual_score_value", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "employee_code",
            "year_month",
            "metric_code",
            name="uq_employee_performance_inputs_a",
        ),
        schema="a_class",
    )
    op.create_index(
        "ix_employee_performance_inputs_a_employee",
        "employee_performance_inputs",
        ["employee_code"],
        unique=False,
        schema="a_class",
    )
    op.create_index(
        "ix_employee_performance_inputs_a_month",
        "employee_performance_inputs",
        ["year_month"],
        unique=False,
        schema="a_class",
    )
    op.create_index(
        "ix_employee_performance_inputs_a_metric",
        "employee_performance_inputs",
        ["metric_code"],
        unique=False,
        schema="a_class",
    )
    op.create_index(
        "ix_employee_performance_inputs_a_status",
        "employee_performance_inputs",
        ["status"],
        unique=False,
        schema="a_class",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_employee_performance_inputs_a_status",
        table_name="employee_performance_inputs",
        schema="a_class",
    )
    op.drop_index(
        "ix_employee_performance_inputs_a_metric",
        table_name="employee_performance_inputs",
        schema="a_class",
    )
    op.drop_index(
        "ix_employee_performance_inputs_a_month",
        table_name="employee_performance_inputs",
        schema="a_class",
    )
    op.drop_index(
        "ix_employee_performance_inputs_a_employee",
        table_name="employee_performance_inputs",
        schema="a_class",
    )
    op.drop_table("employee_performance_inputs", schema="a_class")
