"""Add independent employee target allocation ratios.

Active rows are backfilled by monthly shop ownership: a sole assignee gets
1.0, while shared shops receive an equal split and an auditable source marker.
Historical inactive assignments are retained and receive a safe 1.0 ratio.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260803_target_allocation_ratio"
down_revision = "20260803_shop_account_business_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "employee_shop_assignments",
        sa.Column("target_allocation_ratio", sa.Float(), nullable=True),
        schema="a_class",
    )
    op.add_column(
        "employee_shop_assignments",
        sa.Column("target_allocation_ratio_source", sa.String(length=64), nullable=True),
        schema="a_class",
    )
    op.execute(
        sa.text(
            """
            WITH assignment_counts AS (
                SELECT year_month, platform_code, shop_id, COUNT(*) AS employee_count
                FROM a_class.employee_shop_assignments
                WHERE status = 'active'
                GROUP BY year_month, platform_code, shop_id
            )
            UPDATE a_class.employee_shop_assignments AS assignment
            SET target_allocation_ratio = CASE
                    WHEN assignment_counts.employee_count = 1 THEN 1.0
                    ELSE 1.0 / assignment_counts.employee_count
                END,
                target_allocation_ratio_source = CASE
                    WHEN assignment_counts.employee_count = 1 THEN 'backfill_single'
                    ELSE 'backfill_equal'
                END
            FROM assignment_counts
            WHERE assignment.status = 'active'
              AND assignment.year_month = assignment_counts.year_month
              AND assignment.platform_code = assignment_counts.platform_code
              AND assignment.shop_id = assignment_counts.shop_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE a_class.employee_shop_assignments
            SET target_allocation_ratio = COALESCE(target_allocation_ratio, 1.0),
                target_allocation_ratio_source = COALESCE(
                    target_allocation_ratio_source,
                    CASE
                        WHEN status = 'inactive' THEN 'backfill_inactive_history'
                        ELSE 'backfill_single'
                    END
                )
            WHERE target_allocation_ratio IS NULL
               OR target_allocation_ratio_source IS NULL
            """
        )
    )
    op.alter_column(
        "employee_shop_assignments",
        "target_allocation_ratio",
        existing_type=sa.Float(),
        nullable=False,
        server_default="1.0",
        schema="a_class",
    )
    op.alter_column(
        "employee_shop_assignments",
        "target_allocation_ratio_source",
        existing_type=sa.String(length=64),
        nullable=False,
        server_default="manual",
        schema="a_class",
    )


def downgrade() -> None:
    op.drop_column("employee_shop_assignments", "target_allocation_ratio_source", schema="a_class")
    op.drop_column("employee_shop_assignments", "target_allocation_ratio", schema="a_class")
