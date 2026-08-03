"""Repair target allocation metadata in environments with an older rollout."""

from alembic import op
import sqlalchemy as sa


revision = "20260803_repair_target_allocation_ratio"
down_revision = "20260803_boundary_data_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
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


def downgrade() -> None:
    pass
