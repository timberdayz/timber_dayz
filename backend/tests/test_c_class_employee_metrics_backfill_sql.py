from pathlib import Path


MIGRATION_PATH = Path(
    "migrations/versions/20260415_c_class_employee_metrics_english_columns.py"
)


def test_migration_backfills_employee_performance_from_chinese_columns():
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    assert '"员工编号"' in migration
    assert '"年月"' in migration
    assert '"实际销售额"' in migration
    assert '"达成率"' in migration
    assert '"绩效得分"' in migration
    assert '"计算时间"' in migration
    assert "employee_code" in migration
    assert "actual_sales" in migration


def test_migration_backfills_employee_commissions_from_chinese_columns():
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    assert '"员工编号"' in migration
    assert '"年月"' in migration
    assert '"销售额"' in migration
    assert '"提成金额"' in migration
    assert '"提成比例"' in migration
    assert '"计算时间"' in migration
    assert "commission_amount" in migration
