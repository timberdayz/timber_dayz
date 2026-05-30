"""hr schema alignment cleanup

Revision ID: 20260530_hr_schema_alignment_cleanup
Revises: 20260529_add_operation_target_scope_type
Create Date: 2026-05-30
"""

from alembic import op
import sqlalchemy as sa


revision = "20260530_hr_schema_alignment_cleanup"
down_revision = "20260529_add_operation_target_scope_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "salary_structures",
        sa.Column("remark", sa.Text(), nullable=True),
        schema="a_class",
    )
    op.add_column(
        "performance_scores",
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="c_class",
    )
    op.execute(
        """
        UPDATE c_class.performance_scores
        SET calculated_at = COALESCE(updated_at, created_at, now())
        """
    )
    op.add_column(
        "dim_shops",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        schema="core",
    )

    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY target_type, date_trunc('month', period_start)
                    ORDER BY created_at DESC, id DESC
                ) AS rn
            FROM a_class.sales_targets
            WHERE status = 'active'
              AND target_type IN ('shop', 'product')
        )
        UPDATE a_class.sales_targets st
        SET status = 'inactive',
            updated_at = now()
        FROM ranked r
        WHERE st.id = r.id
          AND r.rn > 1
        """
    )


def downgrade() -> None:
    op.drop_column("dim_shops", "is_active", schema="core")
    op.drop_column("performance_scores", "calculated_at", schema="c_class")
    op.drop_column("salary_structures", "remark", schema="a_class")
