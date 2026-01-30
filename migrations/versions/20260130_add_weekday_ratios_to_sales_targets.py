"""add weekday_ratios to sales_targets

Revision ID: 20260130_weekday_ratios
Revises: 20260130_target_breakdown
Create Date: 2026-01-30

说明:
- sales_targets 表增加 weekday_ratios 列(JSON)，周一到周日拆分比例，用于按比例生成日度目标
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = '20260130_weekday_ratios'
down_revision = '20260130_target_breakdown'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'sales_targets',
        sa.Column('weekday_ratios', JSONB, nullable=True, comment='周一到周日拆分比例 {"1":0.14,...,"7":0.14} 和为1')
    )


def downgrade():
    op.drop_column('sales_targets', 'weekday_ratios')
