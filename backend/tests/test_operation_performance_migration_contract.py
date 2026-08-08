from pathlib import Path


def test_operation_performance_workbench_migration_exists():
    migration = Path("migrations/versions/20260808_operation_performance_workbench.py")

    assert migration.exists()
    content = migration.read_text(encoding="utf-8")
    assert "operation_metric_catalog" in content
    assert "uq_operation_target_month_metric" in content
    assert "enforce_operation_target_contract" in content
    assert "enforce_operation_breakdown_contract" in content
    assert "calculation_status" in content
