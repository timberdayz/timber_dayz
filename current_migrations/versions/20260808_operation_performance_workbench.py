"""Add the monthly operation performance workbench contract."""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20260808_operation_performance_workbench"
down_revision = "current_schema_20260805"
branch_labels = None
depends_on = None


def _columns(connection, table: str, schema: str) -> set[str]:
    return {
        item["name"]
        for item in sa.inspect(connection).get_columns(table, schema=schema)
    }


def _add_column_if_missing(
    connection, table: str, schema: str, column: sa.Column
) -> None:
    if column.name not in _columns(connection, table, schema):
        op.add_column(table, column, schema=schema)


def upgrade() -> None:
    connection = op.get_bind()

    if not sa.inspect(connection).has_table(
        "operation_metric_catalog", schema="a_class"
    ):
        op.create_table(
            "operation_metric_catalog",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column(
                "catalog_version", sa.Integer(), nullable=False, server_default="1"
            ),
            sa.Column("metric_code", sa.String(64), nullable=False),
            sa.Column("metric_name", sa.String(128), nullable=False),
            sa.Column("metric_direction", sa.String(32), nullable=False),
            sa.Column("default_target_value", sa.Float(), nullable=True),
            sa.Column(
                "default_max_score", sa.Float(), nullable=False, server_default="0"
            ),
            sa.Column(
                "default_penalty_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("default_penalty_threshold", sa.Float(), nullable=True),
            sa.Column("default_penalty_per_unit", sa.Float(), nullable=True),
            sa.Column("default_penalty_max", sa.Float(), nullable=True),
            sa.Column(
                "manual_score_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.CheckConstraint(
                "metric_direction IN ('higher_better', 'lower_better', 'manual_score')",
                name="chk_operation_metric_catalog_direction",
            ),
            sa.UniqueConstraint(
                "catalog_version",
                "metric_code",
                name="uq_operation_metric_catalog_version_code",
            ),
            schema="a_class",
        )
        op.create_index(
            "ix_operation_metric_catalog_active",
            "operation_metric_catalog",
            ["is_active", "catalog_version"],
            schema="a_class",
        )

    _add_column_if_missing(
        connection,
        "sales_targets",
        "a_class",
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    _add_column_if_missing(
        connection,
        "sales_targets",
        "a_class",
        sa.Column("metric_catalog_version", sa.Integer(), nullable=True),
    )
    _add_column_if_missing(
        connection,
        "sales_targets",
        "a_class",
        sa.Column("performance_config_id", sa.BigInteger(), nullable=True),
    )
    _add_column_if_missing(
        connection,
        "sales_targets",
        "a_class",
        sa.Column(
            "performance_config_updated_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    _add_column_if_missing(
        connection,
        "target_breakdown",
        "a_class",
        sa.Column("operation_contract_version", sa.Integer(), nullable=True),
    )
    _add_column_if_missing(
        connection,
        "employee_performance_inputs",
        "a_class",
        sa.Column("achieved_value", sa.Float(), nullable=True),
    )
    _add_column_if_missing(
        connection,
        "employee_performance",
        "c_class",
        sa.Column(
            "calculation_status",
            sa.String(32),
            nullable=False,
            server_default="historical_unknown",
        ),
    )
    _add_column_if_missing(
        connection,
        "employee_performance",
        "c_class",
        sa.Column(
            "performance_source_type",
            sa.String(32),
            nullable=False,
            server_default="historical",
        ),
    )

    if "achieved_value" in _columns(
        connection, "employee_performance_inputs", "a_class"
    ):
        op.alter_column(
            "employee_performance_inputs",
            "achieved_value",
            nullable=True,
            schema="a_class",
        )
    if "performance_score" in _columns(connection, "employee_performance", "c_class"):
        op.alter_column(
            "employee_performance", "performance_score", nullable=True, schema="c_class"
        )

    connection.execute(
        sa.text(
            """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_operation_target_month_metric
        ON a_class.sales_targets (period_start, period_end, metric_code)
        WHERE target_type = 'operation'
          AND metric_catalog_version IS NOT NULL
          AND scope_type = 'shop'
          AND metric_code IS NOT NULL
        """
        )
    )
    connection.execute(
        sa.text(
            """
        CREATE OR REPLACE FUNCTION a_class.enforce_operation_target_contract()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.target_type = 'operation' AND NEW.metric_catalog_version IS NOT NULL THEN
                IF NEW.scope_type IS DISTINCT FROM 'shop' THEN
                    RAISE EXCEPTION 'operation targets require scope_type=shop';
                END IF;
                IF NEW.period_start IS NULL OR NEW.period_end IS NULL
                   OR NEW.period_start <> date_trunc('month', NEW.period_start)::date
                   OR NEW.period_end <> (date_trunc('month', NEW.period_start) + interval '1 month - 1 day')::date THEN
                    RAISE EXCEPTION 'operation targets require a complete calendar month';
                END IF;
                IF NULLIF(btrim(NEW.metric_code), '') IS NULL
                   OR NEW.metric_direction IS NULL
                   OR NEW.metric_direction NOT IN ('higher_better', 'lower_better', 'manual_score') THEN
                    RAISE EXCEPTION 'operation targets require a metric code and valid direction';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_enforce_operation_target_contract ON a_class.sales_targets;
        CREATE TRIGGER trg_enforce_operation_target_contract
        BEFORE INSERT OR UPDATE ON a_class.sales_targets
        FOR EACH ROW EXECUTE FUNCTION a_class.enforce_operation_target_contract();
        """
        )
    )
    connection.execute(
        sa.text(
            """
        CREATE OR REPLACE FUNCTION a_class.enforce_operation_breakdown_contract()
        RETURNS trigger AS $$
        DECLARE
            parent_target a_class.sales_targets%ROWTYPE;
        BEGIN
            SELECT * INTO parent_target FROM a_class.sales_targets WHERE id = NEW.target_id;
            IF FOUND
               AND parent_target.target_type = 'operation'
               AND parent_target.metric_catalog_version IS NOT NULL
               AND NEW.operation_contract_version = parent_target.metric_catalog_version THEN
                IF NEW.breakdown_type IS DISTINCT FROM 'shop' THEN
                    RAISE EXCEPTION 'operation targets only allow shop breakdowns';
                END IF;
                IF NULLIF(btrim(NEW.platform_code), '') IS NULL
                   OR NULLIF(btrim(NEW.shop_id), '') IS NULL THEN
                    RAISE EXCEPTION 'operation shop breakdowns require platform_code and shop_id';
                END IF;
                IF NEW.period_start IS DISTINCT FROM parent_target.period_start
                   OR NEW.period_end IS DISTINCT FROM parent_target.period_end THEN
                    RAISE EXCEPTION 'operation shop breakdowns must use the parent calendar month';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_enforce_operation_breakdown_contract ON a_class.target_breakdown;
        CREATE TRIGGER trg_enforce_operation_breakdown_contract
        BEFORE INSERT OR UPDATE ON a_class.target_breakdown
        FOR EACH ROW EXECUTE FUNCTION a_class.enforce_operation_breakdown_contract();
        """
        )
    )
    connection.execute(
        sa.text(
            """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_operation_shop_override
        ON a_class.target_breakdown
            (target_id, operation_contract_version, breakdown_type, platform_code, shop_id)
        WHERE breakdown_type = 'shop' AND operation_contract_version IS NOT NULL
        """
        )
    )

    seed_rows = [
        ("customer_satisfaction", "客户满意度", "higher_better"),
        ("complaint_count", "投诉次数", "lower_better"),
        ("reply_timeliness", "回复及时率", "higher_better"),
        ("training_check", "培训完成", "manual_score"),
        ("exam_score", "考试成绩", "higher_better"),
        ("manual_other", "其他人工指标", "manual_score"),
    ]
    for code, name, direction in seed_rows:
        connection.execute(
            sa.text(
                """
            INSERT INTO a_class.operation_metric_catalog
                (catalog_version, metric_code, metric_name, metric_direction, default_max_score,
                 manual_score_enabled, is_active)
            VALUES (1, :code, :name, :direction, 0, :manual, true)
            ON CONFLICT (catalog_version, metric_code) DO NOTHING
            """
            ),
            {
                "code": code,
                "name": name,
                "direction": direction,
                "manual": direction == "manual_score",
            },
        )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_enforce_operation_breakdown_contract ON a_class.target_breakdown"
        )
    )
    connection.execute(
        sa.text(
            "DROP FUNCTION IF EXISTS a_class.enforce_operation_breakdown_contract()"
        )
    )
    connection.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_enforce_operation_target_contract ON a_class.sales_targets"
        )
    )
    connection.execute(
        sa.text("DROP FUNCTION IF EXISTS a_class.enforce_operation_target_contract()")
    )
    connection.execute(
        sa.text("DROP INDEX IF EXISTS a_class.uq_operation_shop_override")
    )
    connection.execute(
        sa.text("DROP INDEX IF EXISTS a_class.uq_operation_target_month_metric")
    )
    if sa.inspect(connection).has_table("operation_metric_catalog", schema="a_class"):
        op.drop_table("operation_metric_catalog", schema="a_class")
