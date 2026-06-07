"""add collection config templates and batch metadata

Revision ID: 20260605_collection_config_templates_batches
Revises: 20260531_add_template_family_version_variant
Create Date: 2026-06-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260605_collection_config_templates_batches"
down_revision = "20260531_add_template_family_version_variant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collection_config_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("main_account_id", sa.String(length=100), nullable=False),
        sa.Column("granularity", sa.String(length=20), nullable=False, server_default=sa.text("'daily'")),
        sa.Column("default_date_range_type", sa.String(length=32), nullable=False, server_default=sa.text("'yesterday'")),
        sa.Column("default_execution_mode", sa.String(length=20), nullable=False, server_default=sa.text("'headless'")),
        sa.Column("default_schedule_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("default_schedule_cron", sa.String(length=50), nullable=True),
        sa.Column("default_retry_count", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("default_shop_scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["main_account_id"],
            ["core.main_accounts.main_account_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "platform",
            "main_account_id",
            "granularity",
            name="uq_cc_templates_platform_main_granularity",
        ),
        schema="core",
    )
    op.create_index(
        "ix_collection_config_templates_platform",
        "collection_config_templates",
        ["platform"],
        schema="core",
    )
    op.create_index(
        "ix_collection_config_templates_main_account_id",
        "collection_config_templates",
        ["main_account_id"],
        schema="core",
    )
    op.create_index(
        "ix_collection_config_templates_granularity",
        "collection_config_templates",
        ["granularity"],
        schema="core",
    )

    op.add_column(
        "collection_configs",
        sa.Column("template_id", sa.Integer(), nullable=True),
        schema="core",
    )
    op.add_column(
        "collection_configs",
        sa.Column("batch_key", sa.String(length=32), nullable=True),
        schema="core",
    )
    op.add_column(
        "collection_configs",
        sa.Column("batch_status", sa.String(length=20), nullable=False, server_default=sa.text("'draft'")),
        schema="core",
    )
    op.add_column(
        "collection_configs",
        sa.Column("batch_note", sa.Text(), nullable=True),
        schema="core",
    )
    op.add_column(
        "collection_configs",
        sa.Column("batch_shop_overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema="core",
    )
    op.create_foreign_key(
        "fk_collection_configs_template_id",
        "collection_configs",
        "collection_config_templates",
        ["template_id"],
        ["id"],
        source_schema="core",
        referent_schema="core",
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_collection_configs_template_id",
        "collection_configs",
        ["template_id"],
        schema="core",
    )
    op.create_index(
        "ix_collection_configs_batch_key",
        "collection_configs",
        ["batch_key"],
        schema="core",
    )


def downgrade() -> None:
    op.drop_index("ix_collection_configs_batch_key", table_name="collection_configs", schema="core")
    op.drop_index("ix_collection_configs_template_id", table_name="collection_configs", schema="core")
    op.drop_constraint(
        "fk_collection_configs_template_id",
        "collection_configs",
        schema="core",
        type_="foreignkey",
    )
    op.drop_column("collection_configs", "batch_shop_overrides", schema="core")
    op.drop_column("collection_configs", "batch_note", schema="core")
    op.drop_column("collection_configs", "batch_status", schema="core")
    op.drop_column("collection_configs", "batch_key", schema="core")
    op.drop_column("collection_configs", "template_id", schema="core")

    op.drop_index(
        "ix_collection_config_templates_granularity",
        table_name="collection_config_templates",
        schema="core",
    )
    op.drop_index(
        "ix_collection_config_templates_main_account_id",
        table_name="collection_config_templates",
        schema="core",
    )
    op.drop_index(
        "ix_collection_config_templates_platform",
        table_name="collection_config_templates",
        schema="core",
    )
    op.drop_table("collection_config_templates", schema="core")
