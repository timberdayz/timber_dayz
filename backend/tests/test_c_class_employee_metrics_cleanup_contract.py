from pathlib import Path


def test_runtime_no_longer_contains_employee_performance_cn_fallback():
    source = Path("backend/domains/business/routers/hr_commission.py").read_text(encoding="utf-8")
    assert "_load_employee_performance_cn_fallback" not in source


def test_runtime_no_longer_contains_employee_commissions_cn_fallback():
    source = Path("backend/domains/business/routers/hr_commission.py").read_text(encoding="utf-8")
    assert "_load_employee_commissions_cn_fallback" not in source
