"""Merge alias-core and task-center migration heads.

Revision ID: 20260328_task_center_merge
Revises: 20260326_alias_core, 20260328_task_center
Create Date: 2026-03-28
"""


revision = "20260328_task_center_merge"
down_revision = ("20260326_alias_core", "20260328_task_center")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
