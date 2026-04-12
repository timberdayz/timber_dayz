"""merge training related alembic heads

Revision ID: 20260413_merge_training_heads
Revises: 20260410_collection_config_runs, 20260411_add_employee_performance_adjustments, 20260412_training_management
Create Date: 2026-04-13
"""

from __future__ import annotations


revision = "20260413_merge_training_heads"
down_revision = (
    "20260410_collection_config_runs",
    "20260411_add_employee_performance_adjustments",
    "20260412_training_management",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
