from types import SimpleNamespace

from backend.domains.business.routers.hr_employee import (
    _audit_performance_inputs,
    _display_employee_performance,
)


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
                "personal_target_entries": [
                    {
                        "metric_code": "attendance",
                        "metric_name": "Attendance",
                        "target_value": 100,
                        "input_payload": {"actual_value": 95},
                        "max_score": 10,
                        "auto_score": 10,
                        "formula": "actual / target",
                        "completion_status": "completed",
                    }
                ],
            },
        )
    )

    assert payload["performance_score"] == 72.0
    assert payload["calculation_details"]["store_base_score"] == 70.8
    assert payload["calculation_details"]["store_weighted_contribution"] == 56.6
    assert payload["calculation_details"]["personal_target_score"] == 15.0
    assert payload["calculation_details"]["personal_target_entries"][0]["auto_score"] == 10.0
    assert payload["calculation_details"]["personal_target_entries"][0]["input_payload"] == {"actual_value": 95}


def test_controlled_income_audit_uses_snapshot_entries_instead_of_legacy_inputs():
    items = _audit_performance_inputs(
        legacy_rows=[],
        employee_performance=SimpleNamespace(
            performance_source_type="controlled_targets_v1",
            calculation_details={
                "personal_target_entries": [
                    {
                        "metric_code": "attendance",
                        "metric_name": "Attendance",
                        "target_value": 100,
                        "input_payload": {"actual_value": 95},
                        "max_score": 10,
                        "auto_score": 10,
                        "formula": "actual / target",
                        "completion_status": "completed",
                    }
                ]
            },
        ),
    )

    assert items == [
        {
            "metric_code": "attendance",
            "metric_name": "Attendance",
            "metric_direction": None,
            "target_value": 100.0,
            "achieved_value": 95.0,
            "max_score": 10.0,
            "manual_score_enabled": False,
            "manual_score_value": None,
            "auto_score": 10.0,
            "completion_status": "completed",
            "input_payload": {"actual_value": 95},
            "source": "controlled_targets_v1",
            "reason": "actual / target",
        }
    ]
