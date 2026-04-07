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
LEGACY_SCHEMA_NAME = "public"
CONFIG_TABLE_NAME = "collection_configs"
LEGACY_COLLECTION_TABLES = (
    "collection_configs",
    "collection_tasks",
    "collection_task_logs",
    "collection_sync_points",
)


def _table_names(connection, schema_name: str) -> set[str]:
    inspector = sa.inspect(connection)
    try:
        return set(inspector.get_table_names(schema=schema_name))
    except Exception:
        return set()


def _ensure_collection_configs_table(connection) -> None:
    core_table_names = _table_names(connection, SCHEMA_NAME)
    if CONFIG_TABLE_NAME in core_table_names:
        return

    op.create_table(
        CONFIG_TABLE_NAME,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("account_ids", sa.JSON(), nullable=True),
        sa.Column("data_domains", sa.JSON(), nullable=True),
        sa.Column("sub_domains", sa.JSON(), nullable=True),
        sa.Column("granularity", sa.String(length=50), nullable=True),
        sa.Column("date_range_type", sa.String(length=50), nullable=True),
        sa.Column("custom_date_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("custom_date_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "schedule_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("schedule_cron", sa.String(length=100), nullable=True),
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("3"),
        ),
        sa.Column(
            "execution_mode",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'headless'"),
        ),
        sa.Column(
            "is_active",
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
            "name",
            "platform",
            name="uq_collection_configs_name_platform",
        ),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        "ix_collection_configs_platform",
        CONFIG_TABLE_NAME,
        ["platform"],
        unique=False,
        schema=SCHEMA_NAME,
    )
    op.create_index(
        "ix_collection_configs_active",
        CONFIG_TABLE_NAME,
        ["is_active"],
        unique=False,
        schema=SCHEMA_NAME,
    )


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME}"))

    core_table_names = _table_names(connection, SCHEMA_NAME)
    public_table_names = _table_names(connection, LEGACY_SCHEMA_NAME)

    # Fresh-db migration rehearsals still create collection control-plane tables in public
    # from the historical schema snapshot. Move those tables into core before adding
    # newer core-scoped FKs and companion tables.
    for legacy_table_name in LEGACY_COLLECTION_TABLES:
        if legacy_table_name not in core_table_names and legacy_table_name in public_table_names:
            connection.execute(
                sa.text(
                    f"ALTER TABLE {LEGACY_SCHEMA_NAME}.{legacy_table_name} SET SCHEMA {SCHEMA_NAME}"
                )
            )

    table_names = _table_names(connection, SCHEMA_NAME)

    if CONFIG_TABLE_NAME not in table_names:
        _ensure_collection_configs_table(connection)
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
