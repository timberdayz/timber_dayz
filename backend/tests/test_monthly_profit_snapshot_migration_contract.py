from pathlib import Path


def _find_monthly_profit_snapshot_migration() -> Path:
    versions_dir = Path("migrations/versions")
    matches = sorted(versions_dir.glob("*monthly*profit*snapshot*.py"))
    assert matches, "expected a monthly profit snapshot migration in migrations/versions"
    return matches[-1]


def test_monthly_profit_snapshot_migration_exists():
    _find_monthly_profit_snapshot_migration()


def test_monthly_profit_snapshot_migration_creates_snapshot_tables():
    migration_path = _find_monthly_profit_snapshot_migration()
    source = migration_path.read_text(encoding="utf-8")

    assert "monthly_profit_shop_basis_snapshots" in source
    assert "monthly_profit_employee_commission_snapshots" in source
    assert "monthly_profit_employee_performance_snapshots" in source
    assert "monthly_profit_payroll_snapshots" in source
    assert "finance.monthly_profit_settlements.id" in source or "monthly_profit_settlements" in source
