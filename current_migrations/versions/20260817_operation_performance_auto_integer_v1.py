"""Add auto-integer operation scope identity snapshots."""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20260817_operation_performance_auto_integer_v1"
down_revision = "current_schema_20260817_operation_performance_monthly_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table, column in (
        ("operation_metric_catalog", sa.Column("sort_key", sa.Integer(), nullable=True)),
        ("operation_metric_catalog", sa.Column("input_kind", sa.String(length=32), nullable=True)),
        ("operation_metric_catalog", sa.Column("unit", sa.String(length=32), nullable=True)),
        ("operation_metric_catalog", sa.Column("guidance", sa.Text(), nullable=True)),
        ("operation_metric_catalog", sa.Column("scoring_rule_version", sa.String(length=32), nullable=True)),
        ("sales_targets", sa.Column("scoring_model_version", sa.String(length=32), nullable=True)),
        ("sales_targets", sa.Column("operation_rule_snapshot", sa.JSON(), nullable=True)),
        ("target_breakdown", sa.Column("operation_input_payload", sa.JSON(), nullable=True)),
    ):
        op.add_column(table, column, schema="a_class")
    op.add_column(
        "operation_performance_shop_scopes",
        sa.Column("source_shop_account_id", sa.Integer(), nullable=True),
        schema="a_class",
    )
    op.add_column(
        "operation_performance_shop_scopes",
        sa.Column("standard_name_snapshot", sa.String(length=200), nullable=True),
        schema="a_class",
    )
    op.add_column(
        "operation_performance_shop_scopes",
        sa.Column("alias_snapshots", sa.JSON(), nullable=True),
        schema="a_class",
    )
    op.add_column(
        "operation_performance_shop_scopes",
        sa.Column("snapshot_version", sa.Integer(), nullable=True),
        schema="a_class",
    )
    op.add_column(
        "operation_performance_shop_scopes",
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        schema="a_class",
    )
    op.add_column(
        "operation_performance_shop_scopes",
        sa.Column("confirmed_by", sa.String(length=64), nullable=True),
        schema="a_class",
    )
    op.drop_constraint(
        "chk_operation_performance_scope_exclusion_reason",
        "operation_performance_shop_scopes",
        schema="a_class",
        type_="check",
    )
    metric_rows = [
        ("customer_satisfaction", "客户满意度", "higher_better", 100, 10, "percentage", "%", "填写当月客户满意度百分比"),
        ("complaint_count", "投诉次数", "lower_better", 3, 20, "count", "次", "填写当月投诉次数，不高于 3 次即达标"),
        ("reply_timeliness", "回复及时率", "higher_better", 95, 30, "percentage", "%", "填写当月及时回复率百分比"),
        ("training_completion_rate", "培训完成率", "higher_better", 100, 40, "training_counts", "%", "填写已完成人数和应完成人数"),
        ("operation_special_check", "专项运营检查", "manual_score", None, 50, "special_check", "", "选择检查结论；部分完成或未通过必须说明"),
    ]
    bind = op.get_bind()
    for code, name, direction, target, sort_key, input_kind, unit, guidance in metric_rows:
        bind.execute(
            sa.text(
                """
                INSERT INTO a_class.operation_metric_catalog
                    (catalog_version, metric_code, metric_name, metric_direction,
                     default_target_value, default_max_score, manual_score_enabled,
                     sort_key, input_kind, unit, guidance, scoring_rule_version, is_active)
                VALUES
                    (2, :code, :name, :direction, :target, 0, false,
                     :sort_key, :input_kind, :unit, :guidance, 'auto_integer_v1', true)
                ON CONFLICT (catalog_version, metric_code) DO NOTHING
                """
            ),
            {
                "code": code,
                "name": name,
                "direction": direction,
                "target": target,
                "sort_key": sort_key,
                "input_kind": input_kind,
                "unit": unit,
                "guidance": guidance,
            },
        )


def downgrade() -> None:
    op.create_check_constraint(
        "chk_operation_performance_scope_exclusion_reason",
        "operation_performance_shop_scopes",
        "is_included OR NULLIF(btrim(exclusion_reason), '') IS NOT NULL",
        schema="a_class",
    )
    for name in (
        "confirmed_by",
        "confirmed_at",
        "snapshot_version",
        "alias_snapshots",
        "standard_name_snapshot",
        "source_shop_account_id",
    ):
        op.drop_column("operation_performance_shop_scopes", name, schema="a_class")
    for table, name in (
        ("target_breakdown", "operation_input_payload"),
        ("sales_targets", "operation_rule_snapshot"),
        ("sales_targets", "scoring_model_version"),
        ("operation_metric_catalog", "scoring_rule_version"),
        ("operation_metric_catalog", "guidance"),
        ("operation_metric_catalog", "unit"),
        ("operation_metric_catalog", "input_kind"),
        ("operation_metric_catalog", "sort_key"),
    ):
        op.drop_column(table, name, schema="a_class")
