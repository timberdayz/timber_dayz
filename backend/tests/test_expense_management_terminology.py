from pathlib import Path


def test_expense_management_router_describes_marketing_fee_semantics():
    source = Path("backend/routers/expense_management.py").read_text(encoding="utf-8")

    assert "营销费用" in source
