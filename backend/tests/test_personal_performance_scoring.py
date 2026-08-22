import pytest


def test_personal_metric_budget_is_integer_and_gives_remainder_by_sort_key():
    from backend.services.personal_performance_scoring_service import (
        PersonalPerformanceScoringService,
    )

    allocations = PersonalPerformanceScoringService.allocate_integer_budget(
        [
            {"metric_code": "task", "sort_key": 40},
            {"metric_code": "attendance", "sort_key": 10},
            {"metric_code": "training", "sort_key": 20},
        ]
    )

    assert allocations == {"attendance": 7, "training": 7, "task": 6}
    assert sum(allocations.values()) == 20
    assert all(isinstance(score, int) for score in allocations.values())


@pytest.mark.parametrize(
    ("metric", "payload", "expected"),
    [
        (
            {"input_kind": "percentage", "metric_direction": "higher_better", "default_target_value": 100, "max_score": 20},
            {"actual_value": 90},
            18,
        ),
        (
            {"input_kind": "percentage", "metric_direction": "higher_better", "default_target_value": 95, "max_score": 10},
            {"actual_value": 95},
            10,
        ),
        (
            {"input_kind": "training_counts", "metric_direction": "higher_better", "max_score": 10},
            {"completed_count": 0, "required_count": 0},
            10,
        ),
        (
            {"input_kind": "special_task", "metric_direction": "manual_result", "max_score": 7},
            {"result": "partial", "note": "awaiting sign-off"},
            4,
        ),
    ],
)
def test_controlled_personal_metrics_calculate_integer_scores(metric, payload, expected):
    from backend.services.personal_performance_scoring_service import (
        PersonalPerformanceScoringService,
    )

    score, detail = PersonalPerformanceScoringService.calculate_metric_score(
        metric=metric, payload=payload
    )

    assert score == expected
    assert detail["status"] == "calculated"


def test_special_task_requires_note_for_partial_or_failed_result():
    from backend.services.personal_performance_scoring_service import (
        PersonalPerformanceScoringService,
    )

    with pytest.raises(ValueError, match="说明"):
        PersonalPerformanceScoringService.calculate_metric_score(
            metric={"input_kind": "special_task", "max_score": 10},
            payload={"result": "failed"},
        )
