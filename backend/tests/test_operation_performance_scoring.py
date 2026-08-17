import pytest

from backend.services.operation_performance_scoring_service import (
    OperationPerformanceScoringService,
)


def test_allocate_integer_budget_gives_remainder_to_lowest_sort_keys():
    allocations = OperationPerformanceScoringService.allocate_integer_budget(
        [
            {"metric_code": "complaint_count", "sort_key": 20},
            {"metric_code": "customer_satisfaction", "sort_key": 10},
            {"metric_code": "reply_timeliness", "sort_key": 30},
        ]
    )

    assert allocations == {
        "customer_satisfaction": 7,
        "complaint_count": 7,
        "reply_timeliness": 6,
    }


def test_customer_satisfaction_scores_with_half_up_integer_rounding():
    score, detail = OperationPerformanceScoringService.calculate_metric_score(
        metric={
            "metric_code": "customer_satisfaction",
            "input_kind": "percentage",
            "metric_direction": "higher_better",
            "target_value": 100,
            "max_score": 20,
        },
        payload={"actual_value": 90},
    )

    assert score == 18
    assert detail["status"] == "calculated"
    assert detail["achievement_rate"] == 0.9


def test_training_with_zero_required_people_is_complete_without_manual_score():
    score, detail = OperationPerformanceScoringService.calculate_metric_score(
        metric={
            "metric_code": "training_completion_rate",
            "input_kind": "training_counts",
            "metric_direction": "higher_better",
            "target_value": 100,
            "max_score": 10,
        },
        payload={"completed_count": 0, "required_count": 0},
    )

    assert score == 10
    assert detail["achievement_rate"] == 1.0
    assert detail["message"] == "无需培训，按 100% 达成"


def test_special_check_requires_note_for_partial_result():
    with pytest.raises(ValueError, match="说明"):
        OperationPerformanceScoringService.calculate_metric_score(
            metric={
                "metric_code": "operation_special_check",
                "input_kind": "special_check",
                "metric_direction": "manual_score",
                "target_value": None,
                "max_score": 10,
            },
            payload={"result": "partial"},
        )


def test_operation_models_persist_auto_integer_rule_and_input_snapshots():
    from modules.core.db import OperationMetricCatalog, SalesTarget, TargetBreakdown

    assert {"sort_key", "input_kind", "unit", "guidance", "scoring_rule_version"}.issubset(
        OperationMetricCatalog.__table__.c.keys()
    )
    assert {"scoring_model_version", "operation_rule_snapshot"}.issubset(
        SalesTarget.__table__.c.keys()
    )
    assert "operation_input_payload" in TargetBreakdown.__table__.c.keys()


def test_auto_integer_migration_seeds_the_five_controlled_metrics():
    from pathlib import Path

    source = Path(
        "current_migrations/versions/20260817_operation_performance_auto_integer_v1.py"
    ).read_text(encoding="utf-8")

    for metric_code in (
        "customer_satisfaction",
        "complaint_count",
        "reply_timeliness",
        "training_completion_rate",
        "operation_special_check",
    ):
        assert metric_code in source


def test_auto_integer_rule_input_rejects_client_target_and_score_fields():
    from pydantic import ValidationError

    from backend.schemas.target import OperationWorkbenchMetricInput

    with pytest.raises(ValidationError, match="target_value"):
        OperationWorkbenchMetricInput(
            metric_code="customer_satisfaction",
            is_enabled=True,
            target_value=80,
        )


def test_entry_contract_accepts_structured_training_input_only():
    from backend.schemas.target import OperationWorkbenchEntryInput

    entry = OperationWorkbenchEntryInput(
        metric_code="training_completion_rate",
        platform_code="shopee",
        shop_id="S001",
        completed_count=4,
        required_count=5,
    )

    assert entry.completed_count == 4
    assert entry.required_count == 5
