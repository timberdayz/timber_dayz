"""Add main_account_name to core.main_accounts.

Revision ID: 20260403_add_main_account_name
Revises: 20260402_main_shop_accounts
Create Date: 2026-04-03
"""

from alembic import op
import sqlalchemy as sa


revision = "20260403_add_main_account_name"
down_revision = "20260402_main_shop_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "main_accounts",
        sa.Column("main_account_name", sa.String(length=200), nullable=True),
        schema="core",
    )


def downgrade() -> None:
    op.drop_column("main_accounts", "main_account_name", schema="core")
