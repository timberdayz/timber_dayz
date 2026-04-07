"""add platform_accounts indexes for Orders model shop_id mapping

add-metabase-sql-retain-amount-sign: (platform, store_name) and (platform, account_alias)
for JOIN in Orders model when resolving shop_id from store alias.

Revision ID: 20260220_pasi
Revises: 20260217_ctsa
Create Date: 2026-02-20

"""
from alembic import op
from sqlalchemy import text


revision = "20260220_pasi"
down_revision = "20260217_ctsa"
branch_labels = None
depends_on = None


def index_exists(conn, index_name: str, schema: str = "core") -> bool:
    r = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE schemaname = :schema AND indexname = :idx
        )
    """), {"schema": schema, "idx": index_name})
    return r.scalar() or False


def upgrade() -> None:
    conn = op.get_bind()
    if index_exists(conn, "ix_platform_accounts_platform_store_name", "core"):
        return  # idempotent
    op.create_index(
        "ix_platform_accounts_platform_store_name",
        "platform_accounts",
        ["platform", "store_name"],
        schema="core",
    )
    op.create_index(
        "ix_platform_accounts_platform_account_alias",
        "platform_accounts",
        ["platform", "account_alias"],
        schema="core",
    )


def downgrade() -> None:
    conn = op.get_bind()
    if not index_exists(conn, "ix_platform_accounts_platform_store_name", "core"):
        return
    op.drop_index(
        "ix_platform_accounts_platform_store_name",
        table_name="platform_accounts",
        schema="core",
    )
    op.drop_index(
        "ix_platform_accounts_platform_account_alias",
        table_name="platform_accounts",
        schema="core",
    )
