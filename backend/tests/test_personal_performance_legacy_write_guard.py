from types import SimpleNamespace

import pytest

from backend.domains.business.routers import hr_commission


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _Db:
    async def execute(self, _statement):
        return _ScalarResult(SimpleNamespace(calculation_mode="controlled_targets_v1"))


@pytest.mark.asyncio
async def test_controlled_personal_target_month_blocks_legacy_writes():
    response = await hr_commission._controlled_personal_target_write_conflict(
        db=_Db(), year_month="2026-08"
    )

    assert response is not None
    assert response.status_code == 409
    assert b"controlled" in response.body
