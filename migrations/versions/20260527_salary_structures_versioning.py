"""allow salary_structures versioning per employee

Revision ID: 20260527_salary_structures_versioning
Revises: 20260526_add_soft_delete_to_operating_costs
Create Date: 2026-05-27
"""

from alembic import op
from sqlalchemy import text


revision = "20260527_salary_structures_versioning"
down_revision = "20260526_add_soft_delete_to_operating_costs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        text(
            """
            ALTER TABLE a_class.salary_structures
            DROP CONSTRAINT IF EXISTS salary_structures_employee_code_key
            """
        )
    )
    conn.execute(
        text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'uq_salary_structures_employee_effective_date'
                      AND conrelid = 'a_class.salary_structures'::regclass
                ) THEN
                    ALTER TABLE a_class.salary_structures
                    ADD CONSTRAINT uq_salary_structures_employee_effective_date
                    UNIQUE (employee_code, effective_date);
                END IF;
            END$$;
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        text(
            """
            ALTER TABLE a_class.salary_structures
            DROP CONSTRAINT IF EXISTS uq_salary_structures_employee_effective_date
            """
        )
    )
    conn.execute(
        text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'salary_structures_employee_code_key'
                      AND conrelid = 'a_class.salary_structures'::regclass
                ) THEN
                    ALTER TABLE a_class.salary_structures
                    ADD CONSTRAINT salary_structures_employee_code_key
                    UNIQUE (employee_code);
                END IF;
            END$$;
            """
        )
    )
