from types import SimpleNamespace

import pytest

from backend.services.performance_readiness_service import PerformanceReadinessService


def test_controlled_month_readiness_ignores_not_participating_employee():
    PerformanceReadinessService.assert_controlled_employee_rows_ready(
        [SimpleNamespace(employee_code="IN", is_included=True), SimpleNamespace(employee_code="OUT", is_included=False)],
        {"IN": SimpleNamespace(calculation_status="complete", performance_score=80)},
    )


def test_controlled_month_readiness_rejects_partial_participant():
    with pytest.raises(ValueError, match="PARTIAL"):
        PerformanceReadinessService.assert_controlled_employee_rows_ready(
            [SimpleNamespace(employee_code="PARTIAL", is_included=True)],
            {"PARTIAL": SimpleNamespace(calculation_status="partial", performance_score=None)},
        )
