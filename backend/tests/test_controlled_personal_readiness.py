from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.performance_readiness_service import PerformanceReadinessService
from modules.core.db import PersonalPerformanceEmployeeScope, PersonalPerformancePlan


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


@pytest.mark.asyncio
async def test_controlled_month_readiness_rejects_unconfirmed_scope():
    class Result:
        def __init__(self, scalar=None, rows=None):
            self.scalar = scalar
            self.rows = rows or []

        def scalar_one_or_none(self):
            return self.scalar

        def scalars(self):
            return self

        def all(self):
            return self.rows

    async def execute(statement):
        entity = statement.column_descriptions[0].get("entity")
        if entity is PersonalPerformancePlan:
            return Result(
                scalar=SimpleNamespace(
                    id=1,
                    calculation_mode="controlled_targets_v1",
                    scope_confirmed_at=None,
                )
            )
        assert entity is PersonalPerformanceEmployeeScope
        return Result(rows=[])

    with pytest.raises(ValueError, match="scope is not confirmed"):
        await PerformanceReadinessService(
            SimpleNamespace(execute=AsyncMock(side_effect=execute))
        ).assert_month_performance_ready("2026-08")
