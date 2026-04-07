"""add sales_max_score etc to performance_config

Revision ID: 20260201_max_score
Revises: 20260201_core_platform
Create Date: 2026-02-01

达成率对应得分配置：达成率>100%得满分，<=100%得达成率*满分。
"""
from alembic import op
import sqlalchemy as sa


revision = "20260201_max_score"
down_revision = "20260201_core_platform"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # performance_config 位于 public
    op.add_column(
        "performance_config",
        sa.Column("sales_max_score", sa.Integer(), nullable=False, server_default="30"),
    )
    op.add_column(
        "performance_config",
        sa.Column("profit_max_score", sa.Integer(), nullable=False, server_default="25"),
    )
    op.add_column(
        "performance_config",
        sa.Column("key_product_max_score", sa.Integer(), nullable=False, server_default="25"),
    )
    op.add_column(
        "performance_config",
        sa.Column("operation_max_score", sa.Integer(), nullable=False, server_default="20"),
    )


def downgrade() -> None:
    op.drop_column("performance_config", "operation_max_score")
    op.drop_column("performance_config", "key_product_max_score")
    op.drop_column("performance_config", "profit_max_score")
    op.drop_column("performance_config", "sales_max_score")
