from pathlib import Path


def test_payroll_confirmation_acquires_same_month_transaction_lock_before_confirming():
    source = Path("backend/domains/business/routers/hr_salary.py").read_text(encoding="utf-8")
    body = source[source.index("async def confirm_payroll_record"):source.index("async def reopen_payroll_record")]

    assert "acquire_month_transaction_lock" in body
    assert body.index("acquire_month_transaction_lock") < body.index('record.status = "confirmed"')
    assert body.index("assert_month_mutable") < body.index('record.status = "confirmed"')


def test_legacy_employee_month_lock_uses_explicit_period_argument():
    source = Path("backend/domains/business/routers/hr_commission.py").read_text(encoding="utf-8")
    body = source[source.index("async def _employee_month_lock_conflict"):source.index("async def _create_employee_performance_adjustment")]

    assert "year_month=year_month" in body
    assert "rec.year_month" not in body


def test_assignment_delete_locks_before_it_checks_mutability():
    source = Path("backend/domains/business/routers/hr_commission.py").read_text(encoding="utf-8")
    body = source[source.index("async def delete_employee_shop_assignment"):source.index('@router.get("/shop-commission-config")')]

    assert body.index("acquire_month_transaction_lock") < body.index("assert_employee_month_mutable")


def test_store_and_assignment_writes_share_the_month_transaction_lock():
    for path in (
        "backend/services/operation_performance_workbench_service.py",
        "backend/services/shop_target_workbench_service.py",
        "backend/domains/business/routers/hr_commission.py",
    ):
        assert "acquire_month_transaction_lock" in Path(path).read_text(encoding="utf-8")
