"""Add the ROI investment inputs (Stage 2.2).

Two pairs of columns:

* ``finance.sku_operating_profiles.target_roi`` / ``target_roi_source``
  — the **target ROI** the operator intends to bid at.  It belongs on the
  operating profile because that is where the editable workbench parameters
  live (transport type, competitor price, expected selling price …).

* ``finance.sku_profit_estimates.actual_roi`` / ``actual_roi_source``
  — the **platform-reported ROI** the operator copied out of the ad console.
  It belongs on the profit version because that is the point in time the
  number refers to.

Both are nullable on purpose: *not filled in* is a valid state and must never
be replaced by an optimistic default.  The ``*_source`` columns record where
the number came from (``user_input`` / ``migrated_from_legacy_rate`` /
``platform_report``) — the value alone cannot tell a hand-typed number from a
migrated one, and the ROI verdict treats them differently.

The migration is idempotent: every column is guarded by an existence check.
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261119_add_sku_roi_input_columns"
down_revision = "current_schema_20261118_sink_manual_override_to_platform"
branch_labels = None
depends_on = None


#: (schema, table, column, type) —— 新增的四个列。
_NEW_COLUMNS = (
    ("finance", "sku_operating_profiles", "target_roi", sa.Numeric(12, 4)),
    ("finance", "sku_operating_profiles", "target_roi_source", sa.String(32)),
    ("finance", "sku_profit_estimates", "actual_roi", sa.Numeric(12, 4)),
    ("finance", "sku_profit_estimates", "actual_roi_source", sa.String(32)),
)


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str, schema: str) -> bool:
    return _inspector().has_table(table, schema=schema)


def _has_column(table: str, schema: str, name: str) -> bool:
    return _has_table(table, schema) and name in {
        column["name"] for column in _inspector().get_columns(table, schema=schema)
    }


def upgrade() -> None:
    for schema, table, column, column_type in _NEW_COLUMNS:
        if not _has_table(table, schema):
            continue
        if _has_column(table, schema, column):
            continue
        op.add_column(table, sa.Column(column, column_type, nullable=True), schema=schema)


def downgrade() -> None:
    for schema, table, column, _column_type in reversed(_NEW_COLUMNS):
        if not _has_column(table, schema, column):
            continue
        op.drop_column(table, column, schema=schema)
