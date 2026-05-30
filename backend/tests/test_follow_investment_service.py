from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def _load_service_module():
    try:
        return import_module("backend.services.follow_investment_service")
    except ModuleNotFoundError as exc:
        pytest.fail(f"follow investment service module missing: {exc}")


@pytest.mark.asyncio
async def test_list_investments_filters_records_by_period_month_window():
    module = _load_service_module()
    db = SimpleNamespace(execute=AsyncMock())
    service = module.FollowInvestmentService(db)

    async def fake_execute(stmt):
        sql = str(stmt)
        assert "follow_investments" in sql
        assert "contribution_date" in sql
        assert "withdraw_date" in sql
        params = stmt.compile().params
        assert str(params["contribution_date_1"]) == "2026-04-30"
        assert str(params["withdraw_date_1"]) == "2026-04-01"
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))

    service._load_user_names = AsyncMock(return_value={})
    db.execute = AsyncMock(side_effect=fake_execute)

    payload = await service.list_investments(
        platform_code="shopee",
        shop_id="shop-1",
        status="active",
        period_month="2026-04",
    )

    assert payload == []


@pytest.mark.asyncio
async def test_calculate_settlement_rejects_missing_profit_basis_snapshot(monkeypatch):
    module = _load_service_module()
    db = SimpleNamespace(execute=AsyncMock(), add=AsyncMock(), flush=AsyncMock(), commit=AsyncMock())
    service = module.FollowInvestmentService(db)

    monkeypatch.setattr(service, "_load_profit_basis_snapshot", AsyncMock(return_value=None))
    monkeypatch.setattr(service, "_load_active_investments", AsyncMock(return_value=[]))

    with pytest.raises(ValueError, match="profit basis snapshot not found"):
        await service.calculate_settlement(
            year_month="2026-04",
            platform_code="shopee",
            shop_id="shop-1",
            distribution_ratio=0.4,
        )

    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_approve_settlement_rejects_duplicate_approval():
    module = _load_service_module()

    settlement = SimpleNamespace(
        id=12,
        status="approved",
        approved_by="9",
        approved_at="2026-04-06T15:00:00+00:00",
    )

    class _Result:
        def scalar_one_or_none(self):
            return settlement

    db = SimpleNamespace(
        execute=AsyncMock(return_value=_Result()),
        add=AsyncMock(),
        commit=AsyncMock(),
    )
    service = module.FollowInvestmentService(db)

    with pytest.raises(ValueError, match="settlement already approved"):
        await service.approve_settlement(12, "9")


@pytest.mark.asyncio
async def test_reopen_settlement_rejects_non_approved_status():
    module = _load_service_module()

    settlement = SimpleNamespace(
        id=12,
        status="calculated",
        approved_by=None,
        approved_at=None,
    )

    class _Result:
        def scalar_one_or_none(self):
            return settlement

    db = SimpleNamespace(
        execute=AsyncMock(return_value=_Result()),
        commit=AsyncMock(),
    )
    service = module.FollowInvestmentService(db)

    with pytest.raises(ValueError, match="only approved settlement can be reopened"):
        await service.reopen_settlement(12)


@pytest.mark.asyncio
async def test_approve_settlement_writes_approval_log_timestamp():
    module = _load_service_module()

    settlement = SimpleNamespace(
        id=12,
        status="calculated",
        approved_by=None,
        approved_at=None,
    )
    details_result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))

    class _SettlementResult:
        def scalar_one_or_none(self):
            return settlement

    execute = AsyncMock(side_effect=[_SettlementResult(), details_result])
    added = []
    db = SimpleNamespace(
        execute=execute,
        add=lambda record: added.append(record),
        commit=AsyncMock(),
    )
    service = module.FollowInvestmentService(db)

    await service.approve_settlement(12, "system")

    approval_log = next(record for record in added if record.__class__.__name__ == "ApprovalLog")
    assert approval_log.approved_at is not None
