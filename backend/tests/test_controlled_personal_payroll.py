from types import SimpleNamespace

from backend.services.payroll_generation_service import PayrollGenerationService


def test_controlled_partial_performance_has_no_performance_salary_coefficient():
    coefficient = PayrollGenerationService._normalize_performance_coefficient(
        SimpleNamespace(
            performance_source_type="controlled_targets_v1",
            calculation_status="partial",
            performance_score=99,
        )
    )

    assert coefficient == 0
