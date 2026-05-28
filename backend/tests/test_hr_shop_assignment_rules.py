from types import SimpleNamespace

from backend.domains.business.routers.hr_commission import (
    _validate_shop_assignment_ratio_limit,
)


def test_validate_shop_assignment_ratio_limit_rejects_total_above_one():
    existing_rows = [
        SimpleNamespace(
            id=1,
            employee_code="E001",
            commission_ratio=0.6,
            status="active",
            role="supervisor",
        )
    ]

    error = _validate_shop_assignment_ratio_limit(
        existing_rows=existing_rows,
        employee_code="E002",
        commission_ratio=0.5,
        current_assignment_id=None,
    )

    assert error is not None


def test_validate_shop_assignment_ratio_limit_allows_multiple_supervisors_within_limit():
    existing_rows = [
        SimpleNamespace(
            id=1,
            employee_code="E001",
            commission_ratio=0.4,
            status="active",
            role="supervisor",
        )
    ]

    error = _validate_shop_assignment_ratio_limit(
        existing_rows=existing_rows,
        employee_code="E002",
        commission_ratio=0.5,
        current_assignment_id=None,
    )

    assert error is None


def test_validate_shop_assignment_ratio_limit_excludes_current_record_on_update():
    existing_rows = [
        SimpleNamespace(
            id=1,
            employee_code="E001",
            commission_ratio=0.7,
            status="active",
            role="supervisor",
        ),
        SimpleNamespace(
            id=2,
            employee_code="E002",
            commission_ratio=0.2,
            status="active",
            role="operator",
        ),
    ]

    error = _validate_shop_assignment_ratio_limit(
        existing_rows=existing_rows,
        employee_code="E002",
        commission_ratio=0.3,
        current_assignment_id=2,
    )

    assert error is None
