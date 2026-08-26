from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_get_labor_cost_policy_returns_fixed_v2():
    from backend.domains.business.routers.hr_salary import get_labor_cost_policy

    response = await get_labor_cost_policy(
        db=AsyncMock(), current_user=SimpleNamespace(is_superuser=True)
    )

    payload = response
    assert payload["success"] is True
    assert payload["data"]["basis_version"] == "A_PRE_COMMISSION_LABOR_V2"
    assert payload["data"]["policy_mode"] == "single_runtime_basis"
    assert payload["data"]["effective_month"] is None
    assert payload["data"]["v2_basis_version"] == "A_PRE_COMMISSION_LABOR_V2"


async def test_put_labor_cost_policy_is_compatibility_noop(monkeypatch):
    from backend.domains.business.routers import hr_salary

    db = AsyncMock()
    audit_log = AsyncMock()
    monkeypatch.setattr(hr_salary.audit_service, "log_action", audit_log)

    response = await hr_salary.update_labor_cost_policy(
        body=hr_salary.LaborCostPolicyUpdateRequest(effective_month="2026-09"),
        db=db,
        current_user=SimpleNamespace(is_superuser=True, user_id=1),
    )

    payload = response
    assert payload["success"] is True
    assert payload["data"]["basis_version"] == "A_PRE_COMMISSION_LABOR_V2"
    assert payload["data"]["policy_mode"] == "single_runtime_basis"
    assert payload["data"]["effective_month"] is None
    db.commit.assert_not_awaited()
    audit_log.assert_awaited_once()
