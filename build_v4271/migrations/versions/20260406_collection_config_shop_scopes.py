"""add collection config shop scopes

Revision ID: 20260406_collection_config_shop_scopes
Revises: 20260403_sync_progress_submitted
Create Date: 2026-04-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260406_collection_config_shop_scopes"
down_revision = "20260403_sync_progress_submitted"
branch_labels = None
depends_on = None


TABLE_NAME = "collection_config_shop_scopes"
SCHEMA_NAME = "core"


def _table_names(connection, schema_name: str) -> set[str]:
    inspector = sa.inspect(connection)
    try:
        return set(inspector.get_table_names(schema=schema_name))
    except Exception:
        return set()


def upgrade() -> None:
    connection = op.get_bind()
    table_names = _table_names(connection, SCHEMA_NAME)

    if TABLE_NAME not in table_names:
        op.create_table(
            TABLE_NAME,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "config_id",
                sa.Integer(),
                sa.ForeignKey("core.collection_configs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "shop_account_id",
                sa.String(length=100),
                sa.ForeignKey("core.shop_accounts.shop_account_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("data_domains", sa.JSON(), nullable=False),
            sa.Column("sub_domains", sa.JSON(), nullable=True),
            sa.Column(
                "enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.UniqueConstraint(
                "config_id",
                "shop_account_id",
                name="uq_collection_config_shop_scopes_config_shop",
            ),
            schema=SCHEMA_NAME,
        )
        op.create_index(
            "ix_collection_config_shop_scopes_config_id",
            TABLE_NAME,
            ["config_id"],
            unique=False,
            schema=SCHEMA_NAME,
        )
        op.create_index(
            "ix_collection_config_shop_scopes_shop_account_id",
            TABLE_NAME,
            ["shop_account_id"],
            unique=False,
            schema=SCHEMA_NAME,
        )
        op.create_index(
            "ix_collection_config_shop_scopes_enabled",
            TABLE_NAME,
            ["enabled"],
            unique=False,
            schema=SCHEMA_NAME,
        )


def downgrade() -> None:
    connection = op.get_bind()
    table_names = _table_names(connection, SCHEMA_NAME)
    if TABLE_NAME in table_names:
        op.drop_index(
            "ix_collection_config_shop_scopes_enabled",
            table_name=TABLE_NAME,
            schema=SCHEMA_NAME,
        )
        op.drop_index(
            "ix_collection_config_shop_scopes_shop_account_id",
            table_name=TABLE_NAME,
            schema=SCHEMA_NAME,
        )
        op.drop_index(
            "ix_collection_config_shop_scopes_config_id",
            table_name=TABLE_NAME,
            schema=SCHEMA_NAME,
        )
        op.drop_table(TABLE_NAME, schema=SCHEMA_NAME)
