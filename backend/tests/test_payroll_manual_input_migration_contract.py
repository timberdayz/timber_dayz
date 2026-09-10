from pathlib import Path

from modules.core.db import PayrollManualInput


def test_payroll_manual_input_migration_creates_a_class_table_and_backfills_drafts():
    source = Path("migrations/versions/20260909_add_payroll_manual_inputs.py").read_text(
        encoding="utf-8"
    )
    assert 'revision = "20260909_payroll_manual_inputs"' in source
    assert 'down_revision = "20260826_unify_profit_basis_v2"' in source
    assert 'schema="a_class"' in source
    assert "WHERE status = 'draft'" in source
    assert "ON CONFLICT (employee_code, year_month) DO NOTHING" in source
    assert PayrollManualInput.__table__.schema == "a_class"


def test_current_schema_chain_owns_payroll_manual_input_contract():
    source = Path(
        "current_migrations/versions/20260910_payroll_manual_inputs.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "current_schema_20260910_payroll_manual_inputs"' in source
    assert (
        'down_revision = "current_schema_20260910_product_profit_finalization"'
        in source
    )
    assert '"payroll_manual_inputs"' in source
    assert 'schema="a_class"' in source
    assert "WHERE status = 'draft'" in source
    assert "ON CONFLICT (employee_code, year_month) DO NOTHING" in source
