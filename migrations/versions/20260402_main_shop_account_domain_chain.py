"""Create main/shop account canonical tables and migrate platform_accounts.

Revision ID: 20260402_main_shop_accounts
Revises: 20260401_public_alembic_archive
Create Date: 2026-04-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260402_main_shop_accounts"
down_revision = "20260401_public_alembic_archive"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    bind.execute(sa.text("CREATE SCHEMA IF NOT EXISTS core"))

    op.create_table(
        "main_accounts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("main_account_id", sa.String(length=100), nullable=False, unique=True),
        sa.Column("username", sa.String(length=200), nullable=False),
        sa.Column("password_encrypted", sa.Text(), nullable=False),
        sa.Column("login_url", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("extra_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.String(length=100), nullable=True),
        sa.Column("updated_by", sa.String(length=100), nullable=True),
        schema="core",
    )
    op.create_index("ix_main_accounts_platform", "main_accounts", ["platform"], schema="core")
    op.create_index("ix_main_accounts_enabled", "main_accounts", ["enabled"], schema="core")

    op.create_table(
        "shop_accounts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("shop_account_id", sa.String(length=100), nullable=False, unique=True),
        sa.Column("main_account_id", sa.String(length=100), nullable=False),
        sa.Column("store_name", sa.String(length=200), nullable=False),
        sa.Column("platform_shop_id", sa.String(length=256), nullable=True),
        sa.Column("platform_shop_id_status", sa.String(length=32), nullable=False, server_default=sa.text("'missing'")),
        sa.Column("shop_region", sa.String(length=50), nullable=True),
        sa.Column("shop_type", sa.String(length=50), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("extra_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.String(length=100), nullable=True),
        sa.Column("updated_by", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["main_account_id"], ["core.main_accounts.main_account_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("platform", "platform_shop_id", name="uq_shop_accounts_platform_shop_id"),
        schema="core",
    )
    op.create_index("ix_shop_accounts_main_account_id", "shop_accounts", ["main_account_id"], schema="core")
    op.create_index("ix_shop_accounts_platform_shop_id", "shop_accounts", ["platform_shop_id"], schema="core")
    op.create_index("ix_shop_accounts_enabled", "shop_accounts", ["enabled"], schema="core")

    op.create_table(
        "shop_account_aliases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("shop_account_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("alias_value", sa.String(length=256), nullable=False),
        sa.Column("alias_normalized", sa.String(length=256), nullable=False),
        sa.Column("alias_type", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["shop_account_id"], ["core.shop_accounts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("platform", "alias_normalized", "is_active", name="uq_shop_account_aliases_active_alias"),
        schema="core",
    )
    op.create_index("ix_shop_account_aliases_shop_account_id", "shop_account_aliases", ["shop_account_id"], schema="core")
    op.create_index("ix_shop_account_aliases_platform_alias_normalized", "shop_account_aliases", ["platform", "alias_normalized"], schema="core")

    op.create_table(
        "shop_account_capabilities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("shop_account_id", sa.Integer(), nullable=False),
        sa.Column("data_domain", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["shop_account_id"], ["core.shop_accounts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("shop_account_id", "data_domain", name="uq_shop_account_capabilities_domain"),
        schema="core",
    )
    op.create_index("ix_shop_account_capabilities_shop_account_id", "shop_account_capabilities", ["shop_account_id"], schema="core")

    op.create_table(
        "platform_shop_discoveries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("main_account_id", sa.String(length=100), nullable=False),
        sa.Column("detected_store_name", sa.String(length=256), nullable=True),
        sa.Column("detected_platform_shop_id", sa.String(length=256), nullable=True),
        sa.Column("detected_region", sa.String(length=50), nullable=True),
        sa.Column("candidate_shop_account_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'detected_failed'")),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["main_account_id"], ["core.main_accounts.main_account_id"], ondelete="CASCADE"),
        schema="core",
    )
    op.create_index("ix_platform_shop_discoveries_main_account_id", "platform_shop_discoveries", ["main_account_id"], schema="core")
    op.create_index("ix_platform_shop_discoveries_status", "platform_shop_discoveries", ["status"], schema="core")

    bind.execute(
        sa.text(
            """
            INSERT INTO core.main_accounts (
                platform,
                main_account_id,
                username,
                password_encrypted,
                login_url,
                enabled,
                notes,
                extra_config,
                created_at,
                updated_at,
                created_by,
                updated_by
            )
            SELECT DISTINCT
                pa.platform,
                COALESCE(NULLIF(TRIM(pa.parent_account), ''), pa.account_id) AS main_account_id,
                pa.username,
                pa.password_encrypted,
                pa.login_url,
                pa.enabled,
                pa.notes,
                pa.extra_config,
                pa.created_at,
                pa.updated_at,
                pa.created_by,
                pa.updated_by
            FROM core.platform_accounts pa
            ON CONFLICT (main_account_id) DO NOTHING
            """
        )
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO core.shop_accounts (
                platform,
                shop_account_id,
                main_account_id,
                store_name,
                platform_shop_id,
                platform_shop_id_status,
                shop_region,
                shop_type,
                enabled,
                notes,
                extra_config,
                created_at,
                updated_at,
                created_by,
                updated_by
            )
            SELECT
                pa.platform,
                pa.account_id AS shop_account_id,
                COALESCE(NULLIF(TRIM(pa.parent_account), ''), pa.account_id) AS main_account_id,
                pa.store_name,
                pa.shop_id AS platform_shop_id,
                CASE
                    WHEN COALESCE(NULLIF(TRIM(pa.shop_id), ''), '') = '' THEN 'missing'
                    ELSE 'manual_confirmed'
                END AS platform_shop_id_status,
                pa.shop_region,
                pa.shop_type,
                pa.enabled,
                pa.notes,
                jsonb_strip_nulls(
                    COALESCE(pa.extra_config, '{}'::jsonb) || jsonb_build_object(
                        'legacy_proxy_required', pa.proxy_required,
                        'legacy_currency', pa.currency,
                        'legacy_region', pa.region,
                        'legacy_email', pa.email,
                        'legacy_phone', pa.phone
                    )
                ),
                pa.created_at,
                pa.updated_at,
                pa.created_by,
                pa.updated_by
            FROM core.platform_accounts pa
            """
        )
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO core.shop_account_aliases (
                shop_account_id,
                platform,
                alias_value,
                alias_normalized,
                alias_type,
                source,
                is_primary,
                is_active,
                created_at,
                updated_at
            )
            SELECT
                sa.id,
                sa.platform,
                pa.account_alias,
                lower(trim(pa.account_alias)),
                'legacy_account_alias',
                'platform_accounts',
                true,
                true,
                sa.created_at,
                sa.updated_at
            FROM core.platform_accounts pa
            JOIN core.shop_accounts sa
              ON sa.platform = pa.platform
             AND sa.shop_account_id = pa.account_id
            WHERE COALESCE(NULLIF(TRIM(pa.account_alias), ''), '') <> ''
            ON CONFLICT ON CONSTRAINT uq_shop_account_aliases_active_alias DO NOTHING
            """
        )
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO core.shop_account_capabilities (
                shop_account_id,
                data_domain,
                enabled,
                created_at,
                updated_at
            )
            SELECT
                sa.id,
                kv.key,
                COALESCE((kv.value)::boolean, false),
                sa.created_at,
                sa.updated_at
            FROM core.platform_accounts pa
            JOIN core.shop_accounts sa
              ON sa.platform = pa.platform
             AND sa.shop_account_id = pa.account_id
            CROSS JOIN LATERAL jsonb_each(COALESCE(pa.capabilities, '{}'::jsonb)) AS kv(key, value)
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_platform_shop_discoveries_status", table_name="platform_shop_discoveries", schema="core")
    op.drop_index("ix_platform_shop_discoveries_main_account_id", table_name="platform_shop_discoveries", schema="core")
    op.drop_table("platform_shop_discoveries", schema="core")

    op.drop_index("ix_shop_account_capabilities_shop_account_id", table_name="shop_account_capabilities", schema="core")
    op.drop_table("shop_account_capabilities", schema="core")

    op.drop_index("ix_shop_account_aliases_platform_alias_normalized", table_name="shop_account_aliases", schema="core")
    op.drop_index("ix_shop_account_aliases_shop_account_id", table_name="shop_account_aliases", schema="core")
    op.drop_table("shop_account_aliases", schema="core")

    op.drop_index("ix_shop_accounts_enabled", table_name="shop_accounts", schema="core")
    op.drop_index("ix_shop_accounts_platform_shop_id", table_name="shop_accounts", schema="core")
    op.drop_index("ix_shop_accounts_main_account_id", table_name="shop_accounts", schema="core")
    op.drop_table("shop_accounts", schema="core")

    op.drop_index("ix_main_accounts_enabled", table_name="main_accounts", schema="core")
    op.drop_index("ix_main_accounts_platform", table_name="main_accounts", schema="core")
    op.drop_table("main_accounts", schema="core")
