"""add shop_time to target_breakdown breakdown_type

Revision ID: 20260130_shop_time
Revises: 20260130_weekday_ratios
Create Date: 2026-01-30

说明:
- target_breakdown 表 chk_breakdown_type 约束增加 shop_time，用于日度按店铺
"""

from alembic import op


revision = '20260130_shop_time'
down_revision = '20260130_weekday_ratios'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('chk_breakdown_type', 'target_breakdown', schema='a_class', type_='check')
    op.create_check_constraint(
        'chk_breakdown_type',
        'target_breakdown',
        "breakdown_type IN ('shop', 'time', 'shop_time')",
        schema='a_class',
    )


def downgrade():
    op.drop_constraint('chk_breakdown_type', 'target_breakdown', schema='a_class', type_='check')
    op.create_check_constraint(
        'chk_breakdown_type',
        'target_breakdown',
        "breakdown_type IN ('shop', 'time')",
        schema='a_class',
    )
