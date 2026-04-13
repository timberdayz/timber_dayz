from pathlib import Path


def test_expense_contract_and_router_use_only_marketing_fee_fields_in_public_contract():
    schema_source = Path("backend/schemas/expense.py").read_text(encoding="utf-8")
    router_source = Path("backend/routers/expense_management.py").read_text(encoding="utf-8")

    assert "marketing_fee" in schema_source
    assert "total_marketing_fee" in schema_source
    assert '"marketing_fee"' in router_source
    assert '"total_marketing_fee"' in router_source
    assert "total_salary" not in schema_source
    assert 'salary: float' not in schema_source
    assert '"total_salary"' not in router_source
