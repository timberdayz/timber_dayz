"""Add independent employee target allocation ratios.

The upgrade contains the backfill SQL but is intentionally not executed by this
task. Existing assignments receive 1.0 when they are the only employee for a
shop/month, otherwise an equal split by assignment count.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260803_target_allocation_ratio"
down_revision = "20260629_cloud_sync_receive_log"
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
                GROUP BY year_month, platform_code, shop_id
            )
            UPDATE a_class.employee_shop_assignments AS assignment
            SET target_allocation_ratio = CASE
                    WHEN assignment_counts.employee_count = 1 THEN 1.0
                    ELSE 1.0 / assignment_counts.employee_count
                END,
                target_allocation_ratio_source = CASE
                    WHEN assignment_counts.employee_count = 1 THEN 'backfill_single_employee'
                    ELSE 'backfill_equal_split'
                END
            FROM assignment_counts
            WHERE assignment.year_month = assignment_counts.year_month
              AND assignment.platform_code = assignment_counts.platform_code
              AND assignment.shop_id = assignment_counts.shop_id
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
