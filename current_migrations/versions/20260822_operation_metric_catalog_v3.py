"""Add the store-only operation metric catalog V3."""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20260822_operation_metric_catalog_v3"
down_revision = "current_schema_20260822_personal_performance_target_workbench"
branch_labels = None
depends_on = None


def upgrade() -> None:
    metric_rows = (
        (
            "customer_satisfaction",
            "\u5ba2\u6237\u6ee1\u610f\u5ea6",
            "higher_better",
            100,
            10,
            "percentage",
            "%",
            "\u586b\u5199\u5f53\u6708\u5ba2\u6237\u6ee1\u610f\u5ea6\u767e\u5206\u6bd4",
        ),
        (
            "complaint_count",
            "\u6295\u8bc9\u6b21\u6570",
            "lower_better",
            3,
            20,
            "count",
            "\u6b21",
            "\u586b\u5199\u5f53\u6708\u6295\u8bc9\u6b21\u6570\uff0c\u4e0d\u9ad8\u4e8e 3 \u6b21\u5373\u8fbe\u6807",
        ),
        (
            "reply_timeliness",
            "\u56de\u590d\u53ca\u65f6\u7387",
            "higher_better",
            95,
            30,
            "percentage",
            "%",
            "\u586b\u5199\u5f53\u6708\u53ca\u65f6\u56de\u590d\u7387\u767e\u5206\u6bd4",
        ),
        (
            "operation_special_check",
            "\u4e13\u9879\u8fd0\u8425\u68c0\u67e5",
            "manual_score",
            None,
            50,
            "special_check",
            "",
            "\u9009\u62e9\u68c0\u67e5\u7ed3\u8bba\uff1b\u90e8\u5206\u5b8c\u6210\u6216\u672a\u901a\u8fc7\u5fc5\u987b\u8bf4\u660e",
        ),
    )
    connection = op.get_bind()
    for code, name, direction, target, sort_key, input_kind, unit, guidance in metric_rows:
        connection.execute(
            sa.text(
                """
                INSERT INTO a_class.operation_metric_catalog
                    (catalog_version, metric_code, metric_name, metric_direction,
                     default_target_value, default_max_score, manual_score_enabled,
                     sort_key, input_kind, unit, guidance, scoring_rule_version, is_active)
                VALUES
                    (3, :code, :name, :direction, :target, 0, false,
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
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM a_class.sales_targets
                    WHERE target_type = 'operation'
                      AND metric_catalog_version = 3
                ) OR EXISTS (
                    SELECT 1
                    FROM a_class.target_breakdown
                    WHERE operation_contract_version = 3
                ) OR EXISTS (
                    SELECT 1
                    FROM a_class.operation_performance_shop_scopes AS scope
                    JOIN a_class.sales_targets AS target
                      ON target.target_type = 'operation'
                     AND target.metric_catalog_version = 3
                     AND to_char(target.period_start, 'YYYY-MM') = scope.year_month
                ) THEN
                    RAISE EXCEPTION 'cannot downgrade operation metric catalog V3 while rules, scopes, or entries reference it';
                END IF;
            END $$;
            """
        )
    )
    connection.execute(
        sa.text(
            "DELETE FROM a_class.operation_metric_catalog "
            "WHERE catalog_version = 3"
        )
    )
