"""Move account_aliases into core schema and ensure expected indexes exist.

Revision ID: 20260326_alias_core
Revises: 20260324_cloud_sync
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260326_alias_core"
down_revision = "20260324_cloud_sync"
branch_labels = None
depends_on = None


def safe_print(message: str) -> None:
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode("ascii", "replace").decode("ascii"))


def _table_exists(inspector, table_name: str, schema: str | None = None) -> bool:
    return table_name in inspector.get_table_names(schema=schema)


def _index_exists(inspector, table_name: str, index_name: str, schema: str | None = None) -> bool:
    indexes = inspector.get_indexes(table_name, schema=schema)
    return any(index.get("name") == index_name for index in indexes)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    bind.execute(sa.text("CREATE SCHEMA IF NOT EXISTS core"))

    public_exists = _table_exists(inspector, "account_aliases", schema="public")
    core_exists = _table_exists(inspector, "account_aliases", schema="core")

    if public_exists and not core_exists:
        bind.execute(sa.text("ALTER TABLE public.account_aliases SET SCHEMA core"))
        safe_print("[OK] public.account_aliases moved to core.account_aliases")
        inspector = sa.inspect(bind)
        core_exists = True
    elif core_exists:
        safe_print("[SKIP] core.account_aliases already exists")
    else:
        op.create_table(
            "account_aliases",
            sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
            sa.Column("platform", sa.String(length=32), nullable=False),
            sa.Column("data_domain", sa.String(length=64), nullable=False, server_default=sa.text("'orders'")),
            sa.Column("account", sa.String(length=128), nullable=True),
            sa.Column("site", sa.String(length=64), nullable=True),
            sa.Column("store_label_raw", sa.String(length=256), nullable=False),
            sa.Column("target_type", sa.String(length=32), nullable=False, server_default=sa.text("'account'")),
            sa.Column("target_id", sa.String(length=128), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=True, server_default=sa.text("1.0")),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(length=64), nullable=True, server_default=sa.text("'system'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_by", sa.String(length=64), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.PrimaryKeyConstraint("id"),
            schema="core",
        )
        safe_print("[OK] core.account_aliases created")
        inspector = sa.inspect(bind)
        core_exists = True

    if not core_exists:
        raise RuntimeError("core.account_aliases was not created successfully")

    if not _index_exists(inspector, "account_aliases", "uq_account_alias_source", schema="core"):
        op.create_index(
            "uq_account_alias_source",
            "account_aliases",
            ["platform", "data_domain", "account", "site", "store_label_raw"],
            unique=True,
            schema="core",
        )
        safe_print("[OK] created core.uq_account_alias_source")

    if not _index_exists(inspector, "account_aliases", "ix_account_alias_platform_domain", schema="core"):
        op.create_index(
            "ix_account_alias_platform_domain",
            "account_aliases",
            ["platform", "data_domain"],
            unique=False,
            schema="core",
        )
        safe_print("[OK] created core.ix_account_alias_platform_domain")

    if not _index_exists(inspector, "account_aliases", "ix_account_alias_target", schema="core"):
        op.create_index(
            "ix_account_alias_target",
            "account_aliases",
            ["target_id", "active"],
            unique=False,
            schema="core",
        )
        safe_print("[OK] created core.ix_account_alias_target")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, "account_aliases", schema="core") and not _table_exists(inspector, "account_aliases", schema="public"):
        bind.execute(sa.text("ALTER TABLE core.account_aliases SET SCHEMA public"))
        safe_print("[OK] core.account_aliases moved back to public.account_aliases")
