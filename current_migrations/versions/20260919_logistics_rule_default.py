"""Add an explicit default to resolve equal-priority logistics tariffs."""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20260919_logistics_rule_default"
down_revision = "current_schema_20260918_logistics_bill_currency_cny"
branch_labels = None
depends_on = None


def _has_table(table: str, schema: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table, schema=schema)


def _has_column(table: str, schema: str, column: str) -> bool:
    return _has_table(table, schema) and column in {
        item["name"] for item in sa.inspect(op.get_bind()).get_columns(table, schema=schema)
    }


def _has_index(table: str, schema: str, name: str) -> bool:
    return _has_table(table, schema) and any(
        item["name"] == name
        for item in sa.inspect(op.get_bind()).get_indexes(table, schema=schema)
    )


def upgrade() -> None:
    if not _has_table("logistics_provider_rules", "finance"):
        return

    if not _has_column("logistics_provider_rules", "finance", "is_default"):
        op.add_column(
            "logistics_provider_rules",
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
            schema="finance",
        )

    index_name = "uq_logistics_provider_rules_default_scope"
    if not _has_index("logistics_provider_rules", "finance", index_name):
        op.execute(
            "CREATE UNIQUE INDEX uq_logistics_provider_rules_default_scope "
            "ON finance.logistics_provider_rules "
            "(COALESCE(warehouse_code, ''), COALESCE(transport_type, ''), "
            "COALESCE(cargo_class, ''), is_sensitive) "
            "WHERE is_default AND status = 'active' AND effective_to IS NULL"
        )


def downgrade() -> None:
    raise RuntimeError("logistics rule default migration is forward-only")
