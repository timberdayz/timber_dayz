from pathlib import Path


def test_verify_my_income_acceptance_imports_domain_hr_employee_route():
    text = Path("scripts/verify_my_income_acceptance.py").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "backend.domains.business.routers.hr_employee" in text


def test_verify_my_income_acceptance_uses_payroll_breakdown_non_zero_signals():
    text = Path("scripts/verify_my_income_acceptance.py").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert 'breakdown") or {}).get("payroll")' in text
    assert 'performance_salary' in text
    assert 'commission_amount={commission_amount}, performance_salary={performance_salary}' in text


def test_verify_my_income_acceptance_prefers_payroll_records_for_sample_month():
    text = Path("scripts/verify_my_income_acceptance.py").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert 'left join a_class.payroll_records pr' in text
    assert 'coalesce(pr.commission, 0) > 0' in text
    assert 'coalesce(pr.performance_salary, 0) > 0' in text
