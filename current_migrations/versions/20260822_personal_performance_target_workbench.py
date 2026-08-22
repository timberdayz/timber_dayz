"""Add controlled personal performance target persistence."""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20260822_personal_performance_target_workbench"
down_revision = "current_schema_20260817_operation_performance_auto_integer_v1"
branch_labels = None
depends_on = None


def _has_table(connection, table: str, schema: str) -> bool:
    return sa.inspect(connection).has_table(table, schema=schema)


def _columns(connection, table: str, schema: str) -> set[str]:
    return {
        item["name"]
        for item in sa.inspect(connection).get_columns(table, schema=schema)
    }


def upgrade() -> None:
    connection = op.get_bind()

    if not _has_table(connection, "personal_performance_metric_catalog", "a_class"):
        op.create_table(
            "personal_performance_metric_catalog",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("catalog_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("metric_code", sa.String(length=64), nullable=False),
            sa.Column("metric_name", sa.String(length=128), nullable=False),
            sa.Column("metric_direction", sa.String(length=32), nullable=False),
            sa.Column("input_kind", sa.String(length=32), nullable=False),
            sa.Column("default_target_value", sa.Float(), nullable=True),
            sa.Column("unit", sa.String(length=32), nullable=True),
            sa.Column("sort_key", sa.Integer(), nullable=False),
            sa.Column("guidance", sa.Text(), nullable=True),
            sa.Column("scoring_rule_version", sa.String(length=32), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
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
                "metric_direction IN ('higher_better', 'manual_result')",
                name="chk_personal_performance_metric_catalog_direction",
            ),
            sa.CheckConstraint(
                "input_kind IN ('percentage', 'training_counts', 'special_task')",
                name="chk_personal_performance_metric_catalog_input_kind",
            ),
            sa.UniqueConstraint(
                "catalog_version",
                "metric_code",
                name="uq_personal_performance_metric_catalog_version_code",
            ),
            schema="a_class",
        )
        op.create_index(
            "ix_personal_performance_metric_catalog_active",
            "personal_performance_metric_catalog",
            ["is_active", "catalog_version"],
            schema="a_class",
        )

    if not _has_table(connection, "personal_performance_plans", "a_class"):
        op.create_table(
            "personal_performance_plans",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("year_month", sa.String(length=7), nullable=False),
            sa.Column("calculation_mode", sa.String(length=32), nullable=False),
            sa.Column("catalog_version", sa.Integer(), nullable=False),
            sa.Column("scoring_model_version", sa.String(length=32), nullable=False),
            sa.Column("rule_snapshot", sa.JSON(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("scope_confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("scope_confirmed_by", sa.String(length=64), nullable=True),
            sa.Column("created_by", sa.String(length=64), nullable=True),
            sa.Column("updated_by", sa.String(length=64), nullable=True),
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
                "calculation_mode = 'controlled_targets_v1'",
                name="chk_personal_performance_plan_controlled_mode",
            ),
            sa.UniqueConstraint(
                "year_month", name="uq_personal_performance_plan_month"
            ),
            schema="a_class",
        )
        op.create_index(
            "ix_personal_performance_plan_month",
            "personal_performance_plans",
            ["year_month"],
            schema="a_class",
        )

    if not _has_table(connection, "personal_performance_employee_scopes", "a_class"):
        op.create_table(
            "personal_performance_employee_scopes",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("plan_id", sa.BigInteger(), nullable=False),
            sa.Column("employee_code", sa.String(length=64), nullable=False),
            sa.Column("employee_name_snapshot", sa.String(length=128), nullable=False),
            sa.Column("department_name_snapshot", sa.String(length=128), nullable=True),
            sa.Column("position_name_snapshot", sa.String(length=128), nullable=True),
            sa.Column("is_included", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("exclusion_note", sa.String(length=512), nullable=True),
            sa.Column("snapshot_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("confirmed_by", sa.String(length=64), nullable=True),
            sa.Column("created_by", sa.String(length=64), nullable=True),
            sa.Column("updated_by", sa.String(length=64), nullable=True),
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
            sa.ForeignKeyConstraint(
                ["plan_id"],
                ["a_class.personal_performance_plans.id"],
                ondelete="CASCADE",
                name="fk_personal_performance_scope_plan",
            ),
            sa.UniqueConstraint(
                "plan_id",
                "employee_code",
                name="uq_personal_performance_scope_plan_employee",
            ),
            schema="a_class",
        )
        op.create_index(
            "ix_personal_performance_scope_plan_included",
            "personal_performance_employee_scopes",
            ["plan_id", "is_included"],
            schema="a_class",
        )

    if not _has_table(
        connection, "personal_performance_assignment_snapshots", "a_class"
    ):
        op.create_table(
            "personal_performance_assignment_snapshots",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("scope_id", sa.BigInteger(), nullable=False),
            sa.Column("source_assignment_id", sa.BigInteger(), nullable=True),
            sa.Column("platform_code", sa.String(length=32), nullable=False),
            sa.Column("shop_id", sa.String(length=256), nullable=False),
            sa.Column("assignment_ratio_snapshot", sa.Float(), nullable=False),
            sa.Column("role_snapshot", sa.String(length=32), nullable=True),
            sa.Column("sales_target_breakdown_id_snapshot", sa.Integer(), nullable=False),
            sa.Column("sales_target_amount_snapshot", sa.Float(), nullable=False),
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
            sa.ForeignKeyConstraint(
                ["scope_id"],
                ["a_class.personal_performance_employee_scopes.id"],
                ondelete="CASCADE",
                name="fk_personal_performance_assignment_snapshot_scope",
            ),
            sa.ForeignKeyConstraint(
                ["platform_code", "shop_id"],
                ["core.dim_shops.platform_code", "core.dim_shops.shop_id"],
                name="fk_personal_performance_assignment_snapshot_shop",
            ),
            sa.CheckConstraint(
                "assignment_ratio_snapshot >= 0",
                name="chk_personal_performance_assignment_snapshot_ratio",
            ),
            sa.CheckConstraint(
                "sales_target_amount_snapshot > 0",
                name="chk_personal_performance_assignment_snapshot_positive_target",
            ),
            sa.UniqueConstraint(
                "scope_id",
                "platform_code",
                "shop_id",
                name="uq_personal_performance_assignment_snapshot_scope_shop",
            ),
            schema="a_class",
        )
        op.create_index(
            "ix_personal_performance_assignment_snapshot_scope",
            "personal_performance_assignment_snapshots",
            ["scope_id"],
            schema="a_class",
        )

    if not _has_table(connection, "personal_performance_entries", "a_class"):
        op.create_table(
            "personal_performance_entries",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("scope_id", sa.BigInteger(), nullable=False),
            sa.Column("metric_code", sa.String(length=64), nullable=False),
            sa.Column("input_payload", sa.JSON(), nullable=False),
            sa.Column("metric_snapshot", sa.JSON(), nullable=False),
            sa.Column("auto_score", sa.Integer(), nullable=True),
            sa.Column(
                "completion_status",
                sa.String(length=32),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("created_by", sa.String(length=64), nullable=True),
            sa.Column("updated_by", sa.String(length=64), nullable=True),
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
            sa.ForeignKeyConstraint(
                ["scope_id"],
                ["a_class.personal_performance_employee_scopes.id"],
                ondelete="CASCADE",
                name="fk_personal_performance_entry_scope",
            ),
            sa.CheckConstraint(
                "auto_score IS NULL OR (auto_score >= 0 AND auto_score <= 20)",
                name="chk_personal_performance_entry_auto_score",
            ),
            sa.UniqueConstraint(
                "scope_id",
                "metric_code",
                name="uq_personal_performance_entry_scope_metric",
            ),
            schema="a_class",
        )
        op.create_index(
            "ix_personal_performance_entry_scope",
            "personal_performance_entries",
            ["scope_id"],
            schema="a_class",
        )

    if "calculation_details" not in _columns(
        connection, "employee_performance", "c_class"
    ):
        op.add_column(
            "employee_performance",
            sa.Column("calculation_details", sa.JSON(), nullable=True),
            schema="c_class",
        )

    connection.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION a_class.prevent_personal_performance_plan_mode_change()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF NEW.calculation_mode IS DISTINCT FROM OLD.calculation_mode THEN
                    RAISE EXCEPTION 'personal performance plan calculation mode is immutable';
                END IF;
                RETURN NEW;
            END;
            $$;
            """
        )
    )
    connection.execute(
        sa.text(
            """
            DROP TRIGGER IF EXISTS trg_prevent_personal_performance_plan_mode_change
            ON a_class.personal_performance_plans;
            CREATE TRIGGER trg_prevent_personal_performance_plan_mode_change
            BEFORE UPDATE ON a_class.personal_performance_plans
            FOR EACH ROW
            EXECUTE FUNCTION a_class.prevent_personal_performance_plan_mode_change();
            """
        )
    )

    metric_rows = (
        (
            "attendance_compliance_rate",
            "Attendance compliance rate",
            "higher_better",
            "percentage",
            100,
            "%",
            10,
            "Enter the monthly attendance compliance percentage.",
        ),
        (
            "training_completion_rate",
            "Training completion rate",
            "higher_better",
            "training_counts",
            100,
            "%",
            20,
            "Enter completed and required training counts.",
        ),
        (
            "personal_goal_completion_rate",
            "Personal goal completion rate",
            "higher_better",
            "percentage",
            100,
            "%",
            30,
            "Enter the monthly personal goal completion percentage.",
        ),
        (
            "personal_special_task",
            "Personal special task",
            "manual_result",
            "special_task",
            None,
            None,
            40,
            "Choose passed, partial, or failed; partial and failed need a note.",
        ),
    )
    for (
        metric_code,
        metric_name,
        metric_direction,
        input_kind,
        default_target_value,
        unit,
        sort_key,
        guidance,
    ) in metric_rows:
        connection.execute(
            sa.text(
                """
                INSERT INTO a_class.personal_performance_metric_catalog
                    (catalog_version, metric_code, metric_name, metric_direction,
                     input_kind, default_target_value, unit, sort_key, guidance,
                     scoring_rule_version, is_active)
                VALUES
                    (1, :metric_code, :metric_name, :metric_direction,
                     :input_kind, :default_target_value, :unit, :sort_key, :guidance,
                     'controlled_targets_v1', true)
                ON CONFLICT (catalog_version, metric_code) DO NOTHING
                """
            ),
            {
                "metric_code": metric_code,
                "metric_name": metric_name,
                "metric_direction": metric_direction,
                "input_kind": input_kind,
                "default_target_value": default_target_value,
                "unit": unit,
                "sort_key": sort_key,
                "guidance": guidance,
            },
        )


def downgrade() -> None:
    connection = op.get_bind()
    if _has_table(connection, "personal_performance_plans", "a_class"):
        connection.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS trg_prevent_personal_performance_plan_mode_change "
                "ON a_class.personal_performance_plans"
            )
        )
    connection.execute(
        sa.text(
            "DROP FUNCTION IF EXISTS a_class.prevent_personal_performance_plan_mode_change()"
        )
    )

    if "calculation_details" in _columns(
        connection, "employee_performance", "c_class"
    ):
        op.drop_column("employee_performance", "calculation_details", schema="c_class")

    for table in (
        "personal_performance_entries",
        "personal_performance_assignment_snapshots",
        "personal_performance_employee_scopes",
        "personal_performance_plans",
        "personal_performance_metric_catalog",
    ):
        if _has_table(connection, table, "a_class"):
            op.drop_table(table, schema="a_class")
