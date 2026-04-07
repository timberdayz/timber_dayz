"""scope collection configs by main account

Revision ID: 20260406_collection_config_main_account_scope
Revises: 20260406_collection_config_shop_scopes
Create Date: 2026-04-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260406_collection_config_main_account_scope"
down_revision = "20260406_collection_config_shop_scopes"
branch_labels = None
depends_on = None


TABLE_NAME = "collection_configs"
SHOP_SCOPE_TABLE_NAME = "collection_config_shop_scopes"
SCHEMA_NAME = "core"
OLD_UNIQUE = "uq_collection_configs_name_platform"
NEW_UNIQUE = "uq_collection_configs_name_platform_main_account"
MAIN_ACCOUNT_FK = "fk_collection_configs_main_account_id"


def _table_names(connection, schema_name: str) -> set[str]:
    inspector = sa.inspect(connection)
    try:
        return set(inspector.get_table_names(schema=schema_name))
    except Exception:
        return set()


def upgrade() -> None:
    connection = op.get_bind()
    table_names = _table_names(connection, SCHEMA_NAME)

    if SHOP_SCOPE_TABLE_NAME in table_names:
        connection.execute(sa.text(f"DELETE FROM {SCHEMA_NAME}.{SHOP_SCOPE_TABLE_NAME}"))
    if TABLE_NAME in table_names:
        connection.execute(sa.text(f"DELETE FROM {SCHEMA_NAME}.{TABLE_NAME}"))

    with op.batch_alter_table(TABLE_NAME, schema=SCHEMA_NAME) as batch_op:
        batch_op.add_column(sa.Column("main_account_id", sa.String(length=100), nullable=True))

    connection.execute(
        sa.text(
            f"""
            UPDATE {SCHEMA_NAME}.{TABLE_NAME}
            SET main_account_id = '__legacy_config_cleanup__'
            WHERE main_account_id IS NULL
            """
        )
    )

    with op.batch_alter_table(TABLE_NAME, schema=SCHEMA_NAME) as batch_op:
        batch_op.alter_column(
            "main_account_id",
            existing_type=sa.String(length=100),
            nullable=False,
        )
        batch_op.create_foreign_key(
            MAIN_ACCOUNT_FK,
            "main_accounts",
            ["main_account_id"],
            ["main_account_id"],
            referent_schema=SCHEMA_NAME,
            ondelete="CASCADE",
        )
        batch_op.drop_constraint(OLD_UNIQUE, type_="unique")
        batch_op.create_unique_constraint(
            NEW_UNIQUE,
            ["name", "platform", "main_account_id"],
        )
        batch_op.create_index(
            "ix_collection_configs_main_account_id",
            ["main_account_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_collection_configs_platform_main_account_id",
            ["platform", "main_account_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table(TABLE_NAME, schema=SCHEMA_NAME) as batch_op:
        batch_op.drop_index("ix_collection_configs_platform_main_account_id")
        batch_op.drop_index("ix_collection_configs_main_account_id")
        batch_op.drop_constraint(NEW_UNIQUE, type_="unique")
        batch_op.create_unique_constraint(
            OLD_UNIQUE,
            ["name", "platform"],
        )
        batch_op.drop_constraint(MAIN_ACCOUNT_FK, type_="foreignkey")
        batch_op.drop_column("main_account_id")
