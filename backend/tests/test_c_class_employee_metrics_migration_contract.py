from pathlib import Path


def test_employee_performance_english_column_migration_exists():
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("migrations/versions").glob("*.py")
    )
    assert "employee_performance" in source
    assert "employee_code" in source
    assert "actual_sales" in source
    assert "achievement_rate" in source
    assert "performance_score" in source


def test_employee_commissions_english_column_migration_exists():
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("migrations/versions").glob("*.py")
    )
    assert "employee_commissions" in source
    assert "employee_code" in source
    assert "sales_amount" in source
    assert "commission_amount" in source
    assert "commission_rate" in source
