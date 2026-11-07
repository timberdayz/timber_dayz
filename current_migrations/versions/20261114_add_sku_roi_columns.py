"""Add SKU-level ROI columns and close the completeness value domains (Stage 1).

Two things happen here, and they belong in one migration because both touch
``finance.sku_profit_estimates``:

1. **ROI columns.**  A saved profit version must be able to explain the ROI
   numbers an operator acted on, so the break-even ROI, the suggested ROI (raw
   and clamped) and the equivalent legacy ad-rate ROI are stored next to the
   profit breakdown.  All nullable: when the ROI cannot be computed the columns
   stay NULL rather than storing an optimistic number.

   ``expected_selling_price_source`` records whether the measured selling price
   came from the operator ("user_input"), from the operating profile
   ("profile") or from the SKU reference price ("sku_reference").  All three
   look the same in the profit table but they do not carry the same confidence.

2. **C2 completeness constraints.**  Stage 0 fixed the completeness semantics in
   Python only.  Here the same rule is enforced at the database level:
   ``cost_completeness`` and ``actual_recost_completeness`` are two different
   value domains and must not be mixed in one column.

The migration is idempotent: every column and constraint is guarded by an
existence check.
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261114_add_sku_roi_columns"
down_revision = "current_schema_20261113_add_platform_roi_config"
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


def _has_constraint(table: str, schema: str, name: str) -> bool:
    return _has_table(table, schema) and any(
        constraint.get("name") == name
        for constraint in _inspector().get_check_constraints(table, schema=schema)
    )


#: ROI 数值列：分母是商家实收（售价 − 卖家优惠券），与平台 GMV 同一把标尺。
ROI_COLUMNS = (
    ("break_even_roi", sa.Numeric(12, 4)),
    ("suggested_roi", sa.Numeric(12, 4)),
    ("suggested_roi_clamped", sa.Numeric(12, 4)),
    ("equivalent_target_roi", sa.Numeric(12, 4)),
)


def upgrade() -> None:
    if _has_table("sku_operating_profiles", "finance") and not _has_column(
        "sku_operating_profiles", "finance", "expected_selling_price_source"
    ):
        op.add_column(
            "sku_operating_profiles",
            sa.Column("expected_selling_price_source", sa.String(32), nullable=True),
            schema="finance",
        )

    if _has_table("sku_profit_estimates", "finance"):
        if not _has_column(
            "sku_profit_estimates", "finance", "expected_selling_price_source"
        ):
            op.add_column(
                "sku_profit_estimates",
                sa.Column(
                    "expected_selling_price_source", sa.String(32), nullable=True
                ),
                schema="finance",
            )
        for name, column_type in ROI_COLUMNS:
            if not _has_column("sku_profit_estimates", "finance", name):
                op.add_column(
                    "sku_profit_estimates",
                    sa.Column(name, column_type, nullable=True),
                    schema="finance",
                )

        # --- C2：完整度取值域收口 ---
        # 1) 先清洗存量：历史上被 actual_recost 段污染的值归位为 incomplete。
        #    ⚠️ 清洗必须**先于**加约束，否则约束加不上（存量违规）。
        #    生产库与开发库的 sku_profit_estimates 当前都是 0 行，这一步是空操作，
        #    但迁移必须写成对存量非空的情况也成立 —— 哪天有人补录数据就不会卡住。
        op.execute(
            sa.text(
                "UPDATE finance.sku_profit_estimates SET cost_completeness = 'incomplete' "
                "WHERE cost_completeness IS NOT NULL "
                "AND cost_completeness NOT IN ('complete', 'partial', 'incomplete')"
            )
        )
        # 2) 再加 CHECK 约束
        for name, expr in (
            (
                "ck_sku_profit_estimate_cost_completeness",
                "cost_completeness IN ('complete', 'partial', 'incomplete')",
            ),
            (
                "ck_sku_profit_estimate_actual_completeness",
                "actual_recost_completeness IS NULL OR "
                "actual_recost_completeness IN ('incomplete', 'estimated', 'mixed', 'actual')",
            ),
        ):
            if not _has_constraint("sku_profit_estimates", "finance", name):
                op.create_check_constraint(
                    name, "sku_profit_estimates", expr, schema="finance"
                )


def downgrade() -> None:
    # 约束先删，列后删
    if _has_table("sku_profit_estimates", "finance"):
        for name in (
            "ck_sku_profit_estimate_actual_completeness",
            "ck_sku_profit_estimate_cost_completeness",
        ):
            if _has_constraint("sku_profit_estimates", "finance", name):
                op.drop_constraint(
                    name, "sku_profit_estimates", schema="finance", type_="check"
                )
        for name, _column_type in reversed(ROI_COLUMNS):
            if _has_column("sku_profit_estimates", "finance", name):
                op.drop_column("sku_profit_estimates", name, schema="finance")
        if _has_column(
            "sku_profit_estimates", "finance", "expected_selling_price_source"
        ):
            op.drop_column(
                "sku_profit_estimates",
                "expected_selling_price_source",
                schema="finance",
            )

    if _has_table("sku_operating_profiles", "finance") and _has_column(
        "sku_operating_profiles", "finance", "expected_selling_price_source"
    ):
        op.drop_column(
            "sku_operating_profiles",
            "expected_selling_price_source",
            schema="finance",
        )
