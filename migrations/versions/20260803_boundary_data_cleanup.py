"""Finalize operating-store boundary data after account-role rollout."""

from alembic import op
import sqlalchemy as sa


revision = "20260803_boundary_data_cleanup"
down_revision = "20260803_target_allocation_ratio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This is a one-time data classification, not a runtime name-based filter.
    op.execute(
        sa.text(
            """
            UPDATE core.shop_accounts
            SET business_role = 'collection_source', enabled = true
            WHERE shop_account_id = 'miaoshou_real_001'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE a_class.employee_shop_assignments
            SET status = 'inactive', updated_at = now()
            WHERE platform_code = 'miaoshou'
              AND shop_id = 'miaoshou_real_001'
              AND status = 'active'
            """
        )
    )
    op.execute(
        sa.text(
            """
            WITH active_assignment_counts AS (
                SELECT year_month, platform_code, shop_id, COUNT(*) AS employee_count
                FROM a_class.employee_shop_assignments
                WHERE status = 'active'
                GROUP BY year_month, platform_code, shop_id
            )
            UPDATE a_class.employee_shop_assignments AS assignment
            SET target_allocation_ratio = CASE
                    WHEN active_assignment_counts.employee_count = 1 THEN 1.0
                    ELSE 1.0 / active_assignment_counts.employee_count
                END,
                target_allocation_ratio_source = CASE
                    WHEN active_assignment_counts.employee_count = 1 THEN 'backfill_single'
                    ELSE 'backfill_equal'
                END
            FROM active_assignment_counts
            WHERE assignment.status = 'active'
              AND assignment.year_month = active_assignment_counts.year_month
              AND assignment.platform_code = active_assignment_counts.platform_code
              AND assignment.shop_id = active_assignment_counts.shop_id
            """
        )
    )


def downgrade() -> None:
    # Classification and historical allocation backfill are intentionally retained.
    pass
