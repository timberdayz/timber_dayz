"""add performance package amount to salary structures

Revision ID: 20260529_add_salary_structure_performance_package
Revises: 20260527_salary_structures_versioning
Create Date: 2026-05-29
"""

from alembic import op
import sqlalchemy as sa


revision = "20260529_add_salary_structure_performance_package"
down_revision = "20260527_salary_structures_versioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "salary_structures",
        sa.Column(
            "performance_package_amount",
            sa.Numeric(15, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        schema="a_class",
    )


def downgrade() -> None:
    op.drop_column("salary_structures", "performance_package_amount", schema="a_class")
