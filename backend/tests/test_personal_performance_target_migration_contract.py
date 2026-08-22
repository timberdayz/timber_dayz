from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "current_migrations"
    / "versions"
    / "20260822_personal_performance_target_workbench.py"
)


def test_personal_target_migration_extends_the_current_head_without_rewriting_history():
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision = "current_schema_20260822_personal_performance_target_workbench"' in source
    assert 'down_revision = "current_schema_20260817_operation_performance_auto_integer_v1"' in source
    assert "UPDATE a_class.employee_performance_inputs" not in source
    assert "UPDATE a_class.employee_performance_adjustments" not in source
    assert "operation_metric_catalog" not in source


def test_personal_target_migration_creates_reversible_snapshot_tables_and_constraints():
    source = MIGRATION.read_text(encoding="utf-8")

    for table in (
        "personal_performance_metric_catalog",
        "personal_performance_plans",
        "personal_performance_employee_scopes",
        "personal_performance_assignment_snapshots",
        "personal_performance_entries",
    ):
        assert f'"{table}"' in source
        assert table in source[source.index("def downgrade") :]

    for constraint in (
        "uq_personal_performance_metric_catalog_version_code",
        "uq_personal_performance_plan_month",
        "uq_personal_performance_scope_plan_employee",
        "uq_personal_performance_assignment_snapshot_scope_shop",
        "uq_personal_performance_entry_scope_metric",
        "chk_personal_performance_plan_controlled_mode",
    ):
        assert constraint in source

    assert "trg_prevent_personal_performance_plan_mode_change" in source


def test_personal_target_migration_seeds_only_the_approved_controlled_catalog():
    source = MIGRATION.read_text(encoding="utf-8")

    for metric_code in (
        "attendance_compliance_rate",
        "training_completion_rate",
        "personal_goal_completion_rate",
        "personal_special_task",
    ):
        assert metric_code in source

    assert source.count("attendance_compliance_rate") == 1
    assert "management_evaluation" not in source
    assert "manual_score" not in source


def test_personal_target_migration_seeds_chinese_user_facing_metric_names():
    source = MIGRATION.read_text(encoding="utf-8")

    for metric_name in (
        r"\u8003\u52e4\u8fbe\u6807\u7387",
        r"\u57f9\u8bad\u5b8c\u6210\u7387",
        r"\u4e2a\u4eba\u76ee\u6807\u5b8c\u6210\u7387",
        r"\u4e13\u9879\u4efb\u52a1\u5b8c\u6210\u60c5\u51b5",
    ):
        assert metric_name in source
