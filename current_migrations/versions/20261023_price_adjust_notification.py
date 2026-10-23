"""Add the Feishu projection columns for the minimum-price change notification.

One schema change, both nullable:

``ops.feishu_projection_configs.price_adjust_table_id`` / ``price_adjust_base_token``
   Target table for the price-adjustment rows, and the Base that holds it.
   They are separate columns from the three state-mirror table ids on purpose:
   mirrors are upserted by key, the price-adjustment table is append-only
   (the Feishu robot owns archiving).

   The Base token is separate because the price-adjustment table usually lives in
   a **different** Base from the three state mirrors (mirrors in the ERP Base,
   price-adjustment table in the team-collaboration Base). NULL falls back to
   ``FEISHU_PRODUCT_BASE_TOKEN``.

⚠️ The **baseline** columns are NOT here. They live in
``ops.price_adjust_baselines`` (added by
``current_schema_20261024_price_adjust_baseline_table``) because
``core.dim_erp_sku`` is TRUNCATE-and-refilled by the collection→cloud
synchronisation — a baseline living there would be wiped on every sync and
would silently swallow real price changes.

The migration is idempotent: every column is guarded by an existence check.
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261023_price_adjust_notification"
down_revision = "current_schema_20261021_inventory_template_v3"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str, schema: str) -> bool:
    return _inspector().has_table(table, schema=schema)


def _has_column(table: str, schema: str, name: str) -> bool:
    return _has_table(table, schema) and name in {
        column["name"] for column in _inspector().get_columns(table, schema=schema)
    }


def upgrade() -> None:
    if _has_table("feishu_projection_configs", "ops"):
        if not _has_column("feishu_projection_configs", "ops", "price_adjust_table_id"):
            op.add_column(
                "feishu_projection_configs",
                sa.Column("price_adjust_table_id", sa.String(64), nullable=True),
                schema="ops",
            )
        if not _has_column(
            "feishu_projection_configs", "ops", "price_adjust_base_token"
        ):
            op.add_column(
                "feishu_projection_configs",
                sa.Column("price_adjust_base_token", sa.String(64), nullable=True),
                schema="ops",
            )


def downgrade() -> None:
    if _has_table("feishu_projection_configs", "ops"):
        for column in ("price_adjust_base_token", "price_adjust_table_id"):
            if _has_column("feishu_projection_configs", "ops", column):
                op.drop_column("feishu_projection_configs", column, schema="ops")
