from pathlib import Path


def test_employee_labor_cost_allocation_migration_creates_finance_table_and_partial_indexes():
    path = Path("migrations/versions/20260804_add_employee_labor_cost_allocations.py")

    assert path.exists()
    source = path.read_text(encoding="utf-8")
    assert 'revision = "20260804_employee_labor_cost_allocations"' in source
    assert 'down_revision = "20260803_settlement_profit_target"' in source
    assert '"employee_labor_cost_allocations"' in source
    assert '"pre_commission_amount"' in source
    assert '"commission_amount"' in source
    assert "uq_employee_labor_cost_shop_scope" in source
    assert "uq_employee_labor_cost_company_scope" in source
