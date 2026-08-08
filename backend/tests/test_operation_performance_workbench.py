from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.services.operation_performance_workbench_service import (
    OperationMetricCalculator,
    OperationPerformanceWorkbenchService,
)
from modules.core.db import EmployeePerformance, EmployeePerformanceInput, OperationMetricCatalog, SalesTarget


def test_target_router_exposes_operation_workbench_endpoints():
    from backend.domains.business.routers.target_management import router

    routes = {(route.path, tuple(route.methods)) for route in router.routes}
    assert ("/targets/operation-workbench", ("GET",)) in routes
    assert ("/targets/operation-workbench", ("PUT",)) in routes
    assert ("/targets/operation-workbench/copy-prev-month", ("POST",)) in routes


def test_operation_workbench_model_contract_keeps_pending_values_nullable():
    assert hasattr(OperationMetricCatalog, "catalog_version")
    assert hasattr(SalesTarget, "metric_catalog_version")
    assert hasattr(SalesTarget, "performance_config_id")
    assert EmployeePerformanceInput.__table__.c.achieved_value.nullable is True
    assert EmployeePerformance.__table__.c.performance_score.nullable is True
    assert hasattr(EmployeePerformance, "calculation_status")


def test_lower_better_zero_target_scores_zero_actual_at_full_score():
    score, detail = OperationMetricCalculator.calculate(
        SimpleNamespace(
            metric_direction="lower_better",
            target_value=0.0,
            achieved_value=0.0,
            max_score=5.0,
            manual_score_enabled=False,
            manual_score_value=None,
            penalty_enabled=False,
            penalty_threshold=None,
            penalty_per_unit=None,
            penalty_max=None,
        )
    )

    assert score == 5.0
    assert detail["status"] == "calculated"


def test_missing_actual_value_is_pending_instead_of_zero_score():
    score, detail = OperationMetricCalculator.calculate(
        SimpleNamespace(
            metric_direction="higher_better",
            target_value=100.0,
            achieved_value=None,
            max_score=5.0,
            manual_score_enabled=False,
            manual_score_value=None,
            penalty_enabled=False,
            penalty_threshold=None,
            penalty_per_unit=None,
            penalty_max=None,
        )
    )

    assert score is None
    assert detail["status"] == "pending"


def test_penalty_never_makes_operation_metric_negative():
    score, detail = OperationMetricCalculator.calculate(
        SimpleNamespace(
            metric_direction="lower_better",
            target_value=10.0,
            achieved_value=20.0,
            max_score=5.0,
            manual_score_enabled=False,
            manual_score_value=None,
            penalty_enabled=True,
            penalty_threshold=10.0,
            penalty_per_unit=10.0,
            penalty_max=100.0,
        )
    )

    assert score == 0.0
    assert detail["penalty"] == 100.0


def test_aggregate_marks_shop_pending_when_any_enabled_metric_is_incomplete():
    score, details = OperationPerformanceWorkbenchService.aggregate_metrics(
        [
            SimpleNamespace(
                metric_code="reply",
                metric_name="Reply",
                is_enabled=True,
                metric_direction="higher_better",
                target_value=100.0,
                achieved_value=100.0,
                max_score=10.0,
                manual_score_enabled=False,
                manual_score_value=None,
                penalty_enabled=False,
                penalty_threshold=None,
                penalty_per_unit=None,
                penalty_max=None,
            ),
            SimpleNamespace(
                metric_code="complaint",
                metric_name="Complaint",
                is_enabled=True,
                metric_direction="lower_better",
                target_value=0.0,
                achieved_value=None,
                max_score=10.0,
                manual_score_enabled=False,
                manual_score_value=None,
                penalty_enabled=False,
                penalty_threshold=None,
                penalty_per_unit=None,
                penalty_max=None,
            ),
        ],
        expected_max_score=20.0,
    )

    assert score is None
    assert details["status"] == "pending"
    assert len(details["items"]) == 2


def test_aggregate_rejects_score_budget_mismatch():
    with pytest.raises(ValueError, match="运营指标满分之和"):
        OperationPerformanceWorkbenchService.aggregate_metrics(
            [
                SimpleNamespace(
                    metric_code="reply",
                    metric_name="Reply",
                    is_enabled=True,
                    metric_direction="higher_better",
                    target_value=100.0,
                    achieved_value=100.0,
                    max_score=10.0,
                    manual_score_enabled=False,
                    manual_score_value=None,
                    penalty_enabled=False,
                    penalty_threshold=None,
                    penalty_per_unit=None,
                    penalty_max=None,
                )
            ],
            expected_max_score=20.0,
        )


def test_performance_calculation_uses_all_operation_metrics_for_a_shop():
    from backend.domains.business.routers.performance_management import _calculate_operation_metrics_for_shop

    score, detail = _calculate_operation_metrics_for_shop(
        [
            SimpleNamespace(
                metric_code="reply",
                metric_name="Reply",
                is_enabled=True,
                metric_direction="higher_better",
                target_value=100.0,
                achieved_value=100.0,
                max_score=10.0,
                manual_score_enabled=False,
                manual_score_value=None,
                penalty_enabled=False,
                penalty_threshold=None,
                penalty_per_unit=None,
                penalty_max=None,
            ),
            SimpleNamespace(
                metric_code="complaint",
                metric_name="Complaint",
                is_enabled=True,
                metric_direction="lower_better",
                target_value=0.0,
                achieved_value=0.0,
                max_score=10.0,
                manual_score_enabled=False,
                manual_score_value=None,
                penalty_enabled=False,
                penalty_threshold=None,
                penalty_per_unit=None,
                penalty_max=None,
            ),
        ],
        {},
        expected_max_score=20.0,
    )

    assert score == 20.0
    assert detail["status"] == "calculated"
    assert [item["metric_code"] for item in detail["items"]] == ["reply", "complaint"]


def test_readiness_rejects_pending_employee_before_payroll_write():
    from backend.services.performance_readiness_service import (
        PerformanceReadinessError,
        PerformanceReadinessService,
    )

    with pytest.raises(PerformanceReadinessError, match="E001"):
        PerformanceReadinessService.assert_employee_rows_ready(
            {"E001"},
            {
                "E001": SimpleNamespace(
                    calculation_status="pending_store_performance",
                    performance_score=None,
                )
            },
        )


def test_readiness_only_requires_shop_scores_for_shop_inherited_employees():
    from backend.services.performance_readiness_service import PerformanceReadinessService

    assert PerformanceReadinessService.shop_dependent_employee_codes(
        {
            "E001": SimpleNamespace(performance_source_type="personal_inputs"),
            "E002": SimpleNamespace(performance_source_type="shop_inherited"),
        }
    ) == {"E002"}


def test_personal_input_contract_accepts_missing_actual_value():
    from backend.schemas.hr import EmployeePerformanceInputCreate

    payload = EmployeePerformanceInputCreate(
        year_month="2026-08",
        employee_code="E001",
        metric_code="training",
        metric_direction="manual_score",
        target_value=0,
        achieved_value=None,
        max_score=10,
        manual_score_enabled=True,
        manual_score_value=None,
    )

    assert payload.achieved_value is None


def test_operation_workbench_rejects_duplicate_metric_codes_before_write():
    from backend.schemas.target import OperationWorkbenchApplyRequest

    with pytest.raises(ValidationError):
        OperationWorkbenchApplyRequest(
            year_month="2026-08",
            catalog_version=1,
            metrics=[
                {"metric_code": "reply_timeliness", "max_score": 10},
                {"metric_code": "reply_timeliness", "max_score": 10},
            ],
        )


def test_operation_workbench_rejects_duplicate_shop_overrides_before_write():
    from backend.schemas.target import OperationWorkbenchApplyRequest

    with pytest.raises(ValidationError):
        OperationWorkbenchApplyRequest(
            year_month="2026-08",
            catalog_version=1,
            metrics=[{"metric_code": "reply_timeliness", "max_score": 20}],
            shop_overrides=[
                {"metric_code": "reply_timeliness", "platform_code": "shopee", "shop_id": "S001"},
                {"metric_code": "reply_timeliness", "platform_code": "SHOPEE", "shop_id": "S001"},
            ],
        )
