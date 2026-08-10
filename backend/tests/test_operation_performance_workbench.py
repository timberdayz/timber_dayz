from types import SimpleNamespace
from unittest.mock import AsyncMock
from datetime import date

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


def test_runtime_operation_paths_are_isolated_from_legacy_targets():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    workbench_source = (root / "backend/services/operation_performance_workbench_service.py").read_text(encoding="utf-8")
    performance_source = (root / "backend/domains/business/routers/performance_management.py").read_text(encoding="utf-8")
    target_source = (root / "backend/domains/business/routers/target_management.py").read_text(encoding="utf-8")

    assert "SalesTarget.metric_catalog_version.is_not(None)" in workbench_source
    assert "operation_contract_version=target.metric_catalog_version" in workbench_source
    assert "SalesTarget.metric_catalog_version.is_not(None)" in performance_source
    assert "TargetBreakdown.operation_contract_version == SalesTarget.metric_catalog_version" in performance_source
    assert "legacy_operation_breakdowns_by_shop = {}" not in performance_source
    assert "请使用运营绩效工作台" in target_source


@pytest.mark.asyncio
async def test_workbench_override_queries_require_parent_contract_version():
    class _Result:
        def __init__(self, rows=None, scalar=None):
            self.rows = rows or []
            self.scalar_value = scalar

        def scalars(self):
            return self

        def all(self):
            return self.rows

        def scalar_one_or_none(self):
            return self.scalar_value

    class _Db:
        def __init__(self):
            self.statements = []
            self.target = SimpleNamespace(
                id=10,
                metric_code="reply",
                metric_catalog_version=3,
                metric_name="Reply",
                metric_direction="higher_better",
                is_enabled=True,
                target_value=100,
                achieved_value=None,
                max_score=20,
                penalty_enabled=False,
                penalty_threshold=None,
                penalty_per_unit=None,
                penalty_max=None,
                manual_score_enabled=False,
                manual_score_value=None,
                updated_at=None,
            )

        async def execute(self, statement, *_args, **_kwargs):
            self.statements.append(statement)
            statement_text = str(statement)
            if "operation_metric_catalog" in statement_text:
                return _Result(rows=[])
            if "performance_configs" in statement_text:
                return _Result(scalar=None)
            if "target_breakdown" in statement_text:
                return _Result(rows=[])
            if "sales_targets" in statement_text:
                return _Result(rows=[self.target])
            return _Result(rows=[])

    db = _Db()
    await OperationPerformanceWorkbenchService(db).get_workbench("2026-08")

    override_queries = [
        statement for statement in db.statements if "target_breakdown" in str(statement)
    ]
    assert override_queries, "workbench must query shop overrides"
    assert all(
        "operation_contract_version" in str(statement)
        and "metric_catalog_version" in str(statement)
        for statement in override_queries
    )


@pytest.mark.asyncio
async def test_copy_previous_month_reads_only_version_matched_shop_overrides(monkeypatch):
    from backend.services import operation_performance_workbench_service as workbench_module

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return []

    class _Db:
        def __init__(self):
            self.statements = []

        async def execute(self, statement, *_args, **_kwargs):
            self.statements.append(statement)
            return _Result()

    previous = SimpleNamespace(
        id=10,
        metric_code="reply",
        is_enabled=True,
        target_value=100,
        max_score=20,
        penalty_enabled=False,
        penalty_threshold=None,
        penalty_per_unit=None,
        penalty_max=None,
    )
    catalog_item = SimpleNamespace(metric_code="reply", catalog_version=3)

    class _LockService:
        def __init__(self, _db):
            pass

        async def assert_month_mutable(self, **_kwargs):
            return None

    db = _Db()
    service = OperationPerformanceWorkbenchService(db)
    service._targets = AsyncMock(side_effect=[[], [previous]])
    service._catalog = AsyncMock(return_value=[catalog_item])
    service.apply = AsyncMock(return_value={})
    monkeypatch.setattr(workbench_module, "PayrollPeriodLockService", _LockService)

    await service.copy_prev_month("2026-08")

    override_query = next(
        statement for statement in db.statements if "target_breakdown" in str(statement)
    )
    assert "operation_contract_version" in str(override_query)
    assert "metric_catalog_version" in str(override_query)


@pytest.mark.asyncio
async def test_workbench_save_deletes_only_version_matched_shop_overrides(monkeypatch):
    from backend.schemas.target import OperationWorkbenchApplyRequest
    from backend.services import operation_performance_workbench_service as workbench_module

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return []

    class _Db:
        def __init__(self):
            self.statements = []
            self.flush = AsyncMock()
            self.commit = AsyncMock()

        async def execute(self, statement, *_args, **_kwargs):
            self.statements.append(statement)
            return _Result()

        def add(self, _row):
            return None

    class _LockService:
        def __init__(self, _db):
            pass

        async def assert_month_mutable(self, **_kwargs):
            return None

    current = SimpleNamespace(
        id=10,
        metric_code="reply",
        metric_catalog_version=3,
        target_name="Reply",
        target_type="operation",
        scope_type="shop",
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        updated_at=None,
    )
    catalog_item = SimpleNamespace(
        metric_code="reply",
        metric_name="Reply",
        metric_direction="higher_better",
        manual_score_enabled=False,
    )
    config = SimpleNamespace(id=1, operation_max_score=20, updated_at=None)
    db = _Db()
    service = OperationPerformanceWorkbenchService(db)
    service._catalog = AsyncMock(return_value=[catalog_item])
    service._config = AsyncMock(return_value=config)
    service._targets = AsyncMock(return_value=[current])
    service.get_workbench = AsyncMock(return_value={})
    monkeypatch.setattr(workbench_module, "PayrollPeriodLockService", _LockService)

    await service.apply(
        OperationWorkbenchApplyRequest(
            year_month="2026-08",
            catalog_version=3,
            metrics=[{"metric_code": "reply", "max_score": 20}],
        )
    )

    delete_statement = next(
        statement for statement in db.statements if str(statement).startswith("DELETE")
    )
    assert "operation_contract_version" in str(delete_statement)
    assert "metric_catalog_version" in str(delete_statement)


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
