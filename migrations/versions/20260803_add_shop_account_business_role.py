"""Add business role to canonical shop accounts.

Revision ID: 20260803_shop_account_business_role
Revises: 20260629_cloud_sync_receive_log
Create Date: 2026-08-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260803_shop_account_business_role"
down_revision = "20260629_cloud_sync_receive_log"
branch_labels = None
depends_on = None


ROLE_VALUES = ("operating_store", "collection_source")
ROLE_TYPE = sa.Enum(
    *ROLE_VALUES,
    name="shop_account_business_role",
    schema="core",
)


def _table_exists(connection) -> bool:
    return "shop_accounts" in sa.inspect(connection).get_table_names(schema="core")


def _column_exists(connection) -> bool:
    if not _table_exists(connection):
        return False
    return any(
        column["name"] == "business_role"
        for column in sa.inspect(connection).get_columns("shop_accounts", schema="core")
    )


def _role_type_exists(connection) -> bool:
    return any(
        enum["name"] == "shop_account_business_role"
        for enum in sa.inspect(connection).get_enums(schema="core")
    )


def upgrade() -> None:
    connection = op.get_bind()
    op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS core"))

    if not _role_type_exists(connection):
        ROLE_TYPE.create(connection, checkfirst=False)

    if not _column_exists(connection):
        op.add_column(
            "shop_accounts",
            sa.Column(
                "business_role",
                ROLE_TYPE,
                nullable=False,
                server_default=sa.text("'operating_store'"),
            ),
            schema="core",
        )


def downgrade() -> None:
    connection = op.get_bind()
    if _column_exists(connection):
        op.drop_column("shop_accounts", "business_role", schema="core")
    if _role_type_exists(connection):
        ROLE_TYPE.drop(connection, checkfirst=False)
