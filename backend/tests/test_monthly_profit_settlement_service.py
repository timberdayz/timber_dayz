"""月度利润结算 service 的历史用例。

⚠️ 预算制（目标比例 / 目标额 / 差异算法）、审批制（approve / reopen）与快照机制
已随「月度利润看板」下线 ⇒ 打在这些方法上的用例随功能一起删除。
看板新口径的用例见 ``backend/tests/test_finance_dashboard_service.py``。
"""

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

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _ReadyPerformance:
    async def assert_month_performance_ready(self, *_args, **_kwargs):
        return None


def _allow_ready_performance(monkeypatch, module):
    monkeypatch.setattr(
        module, "PerformanceReadinessService", lambda _db: _ReadyPerformance()
    )


@pytest.mark.asyncio
async def test_rebuild_month_ensures_ledger_row_and_writes_adjustment(monkeypatch):
    """rebuild_month 不再重算人员成本：只确保台账行存在 + 写调整项。"""
    module = _load_service_module()
    _allow_ready_performance(monkeypatch, module)
    service = module.MonthlyProfitSettlementService(_make_db())

    record = SimpleNamespace(
        id=11,
        period_month="2026-04",
        net_profit_amount=100000.0,
        personnel_actual_amount=32000.0,
        adjustment_amount=0.0,
        remark=None,
    )
    monkeypatch.setattr(
        service, "_load_settlement_record", AsyncMock(return_value=record)
    )

    captured = {}

    async def fake_upsert(period_month, payload):
        captured["period_month"] = period_month
        captured["payload"] = payload
        return {**payload, "id": 11}

    monkeypatch.setattr(service, "_upsert_settlement", fake_upsert)

    added = []
    service.db.add = lambda row: added.append(row)

    payload = await service.rebuild_month(
        period_month="2026-04",
        adjustment_amount=5000.0,
        adjustment_reason="manual correction",
    )

    assert captured["period_month"] == "2026-04"
    assert captured["payload"]["adjustment_amount"] == pytest.approx(5000.0)
    # 人工调整额仍然从公司留存里扣（看板残差口径未变）
    assert captured["payload"]["company_retained_amount"] == pytest.approx(63000.0)
    assert payload["adjustments"][0]["reason"] == "manual correction"
    assert any(getattr(row, "reason", None) == "manual correction" for row in added)


@pytest.mark.asyncio
async def test_get_month_returns_dashboard_payload(monkeypatch):
    """get_month 与看板同源（旧信封 + 快照视图已下线）。"""
    module = _load_service_module()
    service = module.MonthlyProfitSettlementService(_make_db())

    dashboard = {
        "period_month": "2026-04",
        "net_profit_amount": 100000.0,
        "company_retained_amount": 67000.0,
    }
    get_dashboard = AsyncMock(return_value=dashboard)
    monkeypatch.setattr(service, "get_dashboard", get_dashboard)

    payload = await service.get_month("2026-04")

    assert payload == dashboard
    get_dashboard.assert_awaited_once_with("2026-04")


@pytest.mark.asyncio
async def test_load_personnel_payload_uses_confirmed_post_commission_labor_cost_only():
    module = _load_service_module()
    db = _make_db()
    service = module.MonthlyProfitSettlementService(db)

    allocation_rows = [
        SimpleNamespace(
            id=10,
            employee_code="EMP001",
            allocation_scope="shop",
            platform_code="shopee",
            shop_id="S1",
            performance_amount=6000.0,
            commission_amount=20000.0,
        ),
    ]
    db.execute = AsyncMock(return_value=_ScalarResult(allocation_rows))

    payload = await service._load_personnel_payload("2026-04", {})

    assert payload["actual_amount"] == pytest.approx(26000.0)
    assert payload["details"] == [
        {
            "detail_type": "post_commission_labor_cost",
            "amount": 26000.0,
            "employee_code": "EMP001",
            "platform_code": "shopee",
            "shop_id": "S1",
            "source_module": "employee_labor_cost_allocations",
            "source_record_id": "10",
            "remark": None,
        }
    ]


@pytest.mark.asyncio
async def test_load_personnel_payload_queries_only_locked_labor_allocations():
    """只把「已锁定」的工资单对应的人力成本算进月结人力明细。

    锁定状态集合与 ``backend/services/payroll_period_lock_service.py`` 的
    ``PAYROLL_LOCKED_STATUSES`` 保持一致：**approved / confirmed / paid**。

    （以前这里只认 confirmed + paid，而工资单界面把 approved 也显示成「已锁定」
    —— 两处口径不一致 ⇒ 已审批的工资单会被整月重算悄悄改掉。）
    """
    module = _load_service_module()
    db = _make_db()
    service = module.MonthlyProfitSettlementService(db)

    async def fake_execute(stmt):
        sql = str(stmt)
        assert "employee_labor_cost_allocations" in sql
        assert "period_month" in sql
        assert "source_payroll_status" in sql
        params = stmt.compile().params
        assert any(
            tuple(value) == ("approved", "confirmed", "paid")
            for value in params.values()
        )
        return _ScalarResult([])

    db.execute = AsyncMock(side_effect=fake_execute)

    payload = await service._load_personnel_payload("2026-04", {})

    assert payload["actual_amount"] == pytest.approx(0.0)
    assert payload["details"] == []
