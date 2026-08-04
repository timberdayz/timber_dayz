from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


@pytest.mark.asyncio
async def test_effective_month_selects_v2_only_from_configured_month():
    from backend.services.labor_cost_policy_service import LaborCostPolicyService

    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=_ScalarResult(
            SimpleNamespace(config_value="2026-08")
        )
    )
    service = LaborCostPolicyService(db)

    assert await service.get_profit_basis_version("2026-07") == "A_ONLY_V1"
    assert await service.get_profit_basis_version("2026-08") == "A_PRE_COMMISSION_LABOR_V2"
    assert await service.is_manual_labor_cost_allowed("2026-07") is True
    assert await service.is_manual_labor_cost_allowed("2026-08") is False


@pytest.mark.asyncio
async def test_missing_effective_month_preserves_legacy_behavior():
    from backend.services.labor_cost_policy_service import LaborCostPolicyService

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarResult(None))
    service = LaborCostPolicyService(db)

    assert await service.get_profit_basis_version("2026-08") == "A_ONLY_V1"
    assert await service.is_manual_labor_cost_allowed("2026-08") is True


@pytest.mark.asyncio
async def test_invalid_effective_month_is_rejected():
    from backend.services.labor_cost_policy_service import LaborCostPolicyService

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarResult(None))
    service = LaborCostPolicyService(db)

    with pytest.raises(ValueError, match="YYYY-MM"):
        await service.set_effective_month("2026/08", updated_by_user_id=1)
