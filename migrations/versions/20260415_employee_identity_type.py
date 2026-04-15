"""Add employee identity type to a_class.employees.

Revision ID: 20260415_employee_identity
Revises: 20260415_target_breakdown_ts
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260415_employee_identity"
down_revision = "20260415_target_breakdown_ts"
branch_labels = None
depends_on = None


def _column_exists(connection, schema_name: str, table_name: str, column_name: str) -> bool:
    result = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = :schema_name
              AND table_name = :table_name
              AND column_name = :column_name
            LIMIT 1
            """
        ),
        {
            "schema_name": schema_name,
            "table_name": table_name,
            "column_name": column_name,
        },
    )
    return result.scalar() is not None


def upgrade() -> None:
    connection = op.get_bind()

    if not _column_exists(connection, "a_class", "employees", "employee_identity_type"):
        op.add_column(
            "employees",
            sa.Column(
                "employee_identity_type",
                sa.String(length=32),
                nullable=False,
                server_default="employee",
            ),
            schema="a_class",
        )

    op.execute(
        sa.text(
            """
            UPDATE a_class.employees
            SET employee_identity_type = 'employee'
            WHERE employee_identity_type IS NULL
            """
        )
    )


def downgrade() -> None:
    connection = op.get_bind()

    if _column_exists(connection, "a_class", "employees", "employee_identity_type"):
        op.drop_column("employees", "employee_identity_type", schema="a_class")
