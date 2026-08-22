from types import SimpleNamespace

from backend.domains.business.routers.hr_employee import _display_employee_performance


def test_controlled_income_audit_rounds_scores_and_exposes_calculation_sources():
    payload = _display_employee_performance(
        SimpleNamespace(
            actual_sales=10,
            achievement_rate=0.25,
            performance_score=71.95418558631921,
            calculation_status="complete",
            performance_source_type="controlled_targets_v1",
            calculation_details={
                "store_base_score": 70.756,
                "store_weighted_contribution": 56.6048,
                "personal_target_score": 15,
                "personal_metric_scores": {"attendance": 10, "training": 5},
            },
        )
    )

    assert payload["performance_score"] == 72.0
    assert payload["calculation_details"]["store_base_score"] == 70.8
    assert payload["calculation_details"]["store_weighted_contribution"] == 56.6
    assert payload["calculation_details"]["personal_target_score"] == 15.0
