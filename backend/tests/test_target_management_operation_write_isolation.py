from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from backend.domains.business.routers import target_management
from backend.schemas.target import TargetCreateRequest, TargetUpdateRequest


class _Result:
    def __init__(self, target):
        self.target = target

    def scalar_one_or_none(self):
        return self.target


class _Db:
    def __init__(self, target):
        self.execute = AsyncMock(return_value=_Result(target))
        self.commit = AsyncMock()
        self.rollback = AsyncMock()


def _target(target_type: str = "shop"):
    return SimpleNamespace(
        id=7,
        target_type=target_type,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
    )


@pytest.mark.asyncio
async def test_generic_target_routes_reject_all_operation_write_bypasses(monkeypatch):
    create_db = _Db(None)
    create_request = TargetCreateRequest(
        target_name="legacy operation",
        target_type="operation",
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
    )
    with pytest.raises(HTTPException) as create_error:
        await target_management.create_target(create_request, db=create_db)
    assert create_error.value.status_code == 409
    create_db.commit.assert_not_awaited()

    update_db = _Db(_target())
    with pytest.raises(HTTPException) as update_error:
        await target_management.update_target(
            7,
            TargetUpdateRequest(target_type="operation"),
            db=update_db,
        )
    assert update_error.value.status_code == 409
    update_db.commit.assert_not_awaited()

    operation_db = _Db(_target("operation"))
    with pytest.raises(HTTPException) as daily_error:
        await target_management.generate_daily_breakdown(7, db=operation_db)
    assert daily_error.value.status_code == 409
    operation_db.commit.assert_not_awaited()

    class _UnexpectedService:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("operation calculation must be rejected before service execution")

    monkeypatch.setattr(target_management, "TargetManagementService", _UnexpectedService, raising=False)
    calculate_db = _Db(_target("operation"))
    with pytest.raises(HTTPException) as calculate_error:
        await target_management.calculate_target_achievement(7, db=calculate_db)
    assert calculate_error.value.status_code == 409
    calculate_db.commit.assert_not_awaited()
