from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def _load_service_module():
    try:
        return import_module("backend.services.monthly_profit_settlement_service")
    except ModuleNotFoundError as exc:
        pytest.fail(f"monthly profit settlement service module missing: {exc}")


def _make_db():
    return SimpleNamespace(
        execute=AsyncMock(),
        flush=AsyncMock(),
        commit=AsyncMock(),
        add=lambda record: None,
    )


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_rebuild_monthly_profit_settlement_aggregates_company_totals(monkeypatch):
    module = _load_service_module()
    service = module.MonthlyProfitSettlementService(_make_db())

    async def fake_load_net_profit_amount(period_month):
        assert period_month == "2026-04"
        return 100000.0

    async def fake_load_personnel_payload(period_month):
        assert period_month == "2026-04"
        return {
            "actual_amount": 32000.0,
            "details": [
                {"detail_type": "shop_commission", "amount": 12000.0},
                {"detail_type": "payroll_total_cost", "amount": 20000.0},
            ],
        }

    async def fake_load_follow_payload(period_month):
        assert period_month == "2026-04"
        return {
            "actual_amount": 18000.0,
            "details": [
                {"investor_user_id": 101, "amount": 10000.0},
                {"investor_user_id": 102, "amount": 8000.0},
            ],
        }

    captured = {}

    async def fake_upsert(period_month, payload):
        captured["period_month"] = period_month
        captured["payload"] = payload
        return {**payload, "id": 11}

    monkeypatch.setattr(service, "_load_net_profit_amount", fake_load_net_profit_amount)
    monkeypatch.setattr(service, "_load_personnel_payload", fake_load_personnel_payload)
    monkeypatch.setattr(service, "_load_follow_payload", fake_load_follow_payload)
    monkeypatch.setattr(service, "_upsert_settlement", fake_upsert)

    payload = await service.rebuild_month(
        period_month="2026-04",
        personnel_target_ratio=0.3,
        follow_target_ratio=0.2,
        company_target_ratio=0.5,
        adjustment_amount=0.0,
    )

    assert captured["period_month"] == "2026-04"
    assert payload["summary"]["net_profit_amount"] == pytest.approx(100000.0)
    assert payload["summary"]["personnel_actual_amount"] == pytest.approx(32000.0)
    assert payload["summary"]["follow_actual_amount"] == pytest.approx(18000.0)
    assert payload["summary"]["company_actual_amount"] == pytest.approx(50000.0)
    assert payload["summary"]["personnel_target_amount"] == pytest.approx(30000.0)
    assert payload["summary"]["follow_target_amount"] == pytest.approx(20000.0)
    assert payload["summary"]["company_target_amount"] == pytest.approx(50000.0)


@pytest.mark.asyncio
async def test_rebuild_monthly_profit_settlement_uses_adjustments_in_company_actual(monkeypatch):
    module = _load_service_module()
    service = module.MonthlyProfitSettlementService(_make_db())

    monkeypatch.setattr(service, "_load_net_profit_amount", AsyncMock(return_value=85000.0))
    monkeypatch.setattr(
        service,
        "_load_personnel_payload",
        AsyncMock(return_value={"actual_amount": 25000.0, "details": []}),
    )
    monkeypatch.setattr(
        service,
        "_load_follow_payload",
        AsyncMock(return_value={"actual_amount": 15000.0, "details": []}),
    )
    monkeypatch.setattr(
        service,
        "_upsert_settlement",
        AsyncMock(side_effect=lambda period_month, payload: {**payload, "id": 9}),
    )

    payload = await service.rebuild_month(
        period_month="2026-04",
        personnel_target_ratio=0.35,
        follow_target_ratio=0.15,
        company_target_ratio=0.5,
        adjustment_amount=5000.0,
        adjustment_reason="manual correction",
    )

    assert payload["summary"]["company_actual_amount"] == pytest.approx(40000.0)
    assert payload["summary"]["difference_amount"] == pytest.approx(2500.0)
    assert payload["adjustments"][0]["reason"] == "manual correction"


def test_build_summary_derives_target_amounts_and_actual_ratios():
    module = _load_service_module()
    service = module.MonthlyProfitSettlementService(_make_db())

    summary = service.build_summary(
        period_month="2026-04",
        net_profit_amount=100000.0,
        personnel_actual_amount=28000.0,
        follow_actual_amount=22000.0,
        adjustment_amount=0.0,
        personnel_target_ratio=0.3,
        follow_target_ratio=0.2,
        company_target_ratio=0.5,
    )

    assert summary["personnel_target_amount"] == pytest.approx(30000.0)
    assert summary["follow_target_amount"] == pytest.approx(20000.0)
    assert summary["company_target_amount"] == pytest.approx(50000.0)
    assert summary["personnel_actual_ratio"] == pytest.approx(0.28)
    assert summary["follow_actual_ratio"] == pytest.approx(0.22)
    assert summary["company_actual_ratio"] == pytest.approx(0.5)


def test_build_summary_rejects_target_ratios_that_do_not_sum_to_one():
    module = _load_service_module()
    service = module.MonthlyProfitSettlementService(_make_db())

    with pytest.raises(ValueError, match="target ratios must sum to 1"):
        service.build_summary(
            period_month="2026-04",
            net_profit_amount=100000.0,
            personnel_actual_amount=32000.0,
            follow_actual_amount=18000.0,
            adjustment_amount=0.0,
            personnel_target_ratio=0.3,
            follow_target_ratio=0.2,
            company_target_ratio=0.4,
        )


@pytest.mark.asyncio
async def test_get_monthly_profit_settlement_returns_existing_record(monkeypatch):
    module = _load_service_module()
    service = module.MonthlyProfitSettlementService(_make_db())

    record = {
        "id": 12,
        "period_month": "2026-04",
        "status": "approved",
        "net_profit_amount": 100000.0,
    }

    monkeypatch.setattr(service, "_load_settlement_record", AsyncMock(return_value=record))
    monkeypatch.setattr(service, "_load_personnel_details", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_load_follow_details", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_load_adjustments", AsyncMock(return_value=[]))

    payload = await service.get_month("2026-04")

    assert payload["summary"]["id"] == 12
    assert payload["summary"]["status"] == "approved"
    assert payload["summary"]["period_month"] == "2026-04"


@pytest.mark.asyncio
async def test_load_follow_payload_expands_investor_level_details():
    module = _load_service_module()
    db = _make_db()
    service = module.MonthlyProfitSettlementService(db)

    detail_rows = [
        SimpleNamespace(investor_user_id=101, source_settlement_id=5, approved_income=6000.0, estimated_income=6500.0, status="approved"),
        SimpleNamespace(investor_user_id=102, source_settlement_id=5, approved_income=4000.0, estimated_income=4500.0, status="approved"),
    ]
    db.execute = AsyncMock(return_value=_ScalarResult(detail_rows))

    payload = await service._load_follow_payload("2026-04")

    assert payload["actual_amount"] == pytest.approx(10000.0)
    assert payload["details"] == [
        {
            "investor_user_id": 101,
            "source_settlement_id": 5,
            "amount": 6000.0,
            "status": "approved",
            "remark": None,
        },
        {
            "investor_user_id": 102,
            "source_settlement_id": 5,
            "amount": 4000.0,
            "status": "approved",
            "remark": None,
        },
    ]


@pytest.mark.asyncio
async def test_load_follow_payload_preserves_zero_approved_income():
    module = _load_service_module()
    db = _make_db()
    service = module.MonthlyProfitSettlementService(db)

    detail_rows = [
        SimpleNamespace(investor_user_id=101, source_settlement_id=5, approved_income=0.0, estimated_income=6500.0, status="approved"),
    ]
    db.execute = AsyncMock(return_value=_ScalarResult(detail_rows))

    payload = await service._load_follow_payload("2026-04")

    assert payload["actual_amount"] == pytest.approx(0.0)
    assert payload["details"][0]["amount"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_load_personnel_payload_uses_only_payroll_total_cost():
    module = _load_service_module()
    db = _make_db()
    service = module.MonthlyProfitSettlementService(db)

    payroll_rows = [
        SimpleNamespace(id=10, employee_code="EMP001", total_cost=26000.0),
    ]
    db.execute = AsyncMock(return_value=_ScalarResult(payroll_rows))

    payload = await service._load_personnel_payload("2026-04")

    assert payload["actual_amount"] == pytest.approx(26000.0)
    assert payload["details"] == [
        {
            "detail_type": "payroll_total_cost",
            "amount": 26000.0,
            "employee_code": "EMP001",
            "source_module": "payroll_records",
            "source_record_id": "10",
            "remark": None,
        }
    ]


@pytest.mark.asyncio
async def test_approve_rejects_duplicate_approval():
    module = _load_service_module()
    db = _make_db()
    service = module.MonthlyProfitSettlementService(db)
    db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(status="approved")))

    with pytest.raises(ValueError, match="already approved"):
        await service.approve(12, "9")


@pytest.mark.asyncio
async def test_reopen_rejects_non_approved_settlement():
    module = _load_service_module()
    db = _make_db()
    service = module.MonthlyProfitSettlementService(db)
    db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(status="draft")))

    with pytest.raises(ValueError, match="only approved settlement can be reopened"):
        await service.reopen(12)


@pytest.mark.asyncio
async def test_approve_rejects_when_difference_exceeds_threshold():
    module = _load_service_module()
    db = _make_db()
    service = module.MonthlyProfitSettlementService(db)
    record = SimpleNamespace(
        status="draft",
        difference_amount=5000.0,
        difference_ratio=0.02,
        approved_by=None,
        approved_at=None,
        locked_at=None,
    )
    db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: record))

    with pytest.raises(ValueError, match="difference threshold exceeded"):
        await service.approve(12, "9")


@pytest.mark.asyncio
async def test_update_targets_persists_adjustment_reason(monkeypatch):
    module = _load_service_module()
    db = _make_db()
    service = module.MonthlyProfitSettlementService(db)
    record = SimpleNamespace(
        id=12,
        period_month="2026-04",
        net_profit_amount=100000.0,
        personnel_actual_amount=32000.0,
        follow_actual_amount=18000.0,
        adjustment_amount=0.0,
        personnel_target_ratio=0.3,
        follow_target_ratio=0.2,
        company_target_ratio=0.5,
        status="draft",
        approved_by=None,
        remark=None,
    )
    db.execute = AsyncMock(side_effect=[
        SimpleNamespace(scalar_one_or_none=lambda: record),
        None,
    ])
    added = []
    db.add = lambda row: added.append(row)
    monkeypatch.setattr(service, "_load_personnel_details", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_load_follow_details", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_load_adjustments", AsyncMock(return_value=[
        {
            "adjustment_type": "manual_adjustment",
            "amount": 1200.0,
            "reason": "finance note",
            "created_by": "system",
        }
    ]))

    payload = await service.update_targets(12, {
        "personnel_target_ratio": 0.3,
        "follow_target_ratio": 0.2,
        "company_target_ratio": 0.5,
        "adjustment_amount": 1200.0,
        "adjustment_reason": "finance note",
    })

    assert payload["adjustments"][0]["reason"] == "finance note"
    assert any(getattr(row, "reason", None) == "finance note" for row in added)
