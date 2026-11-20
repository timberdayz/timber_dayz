"""月度利润看板（只读口径）的 service 层契约测试。

口径与理由见 ``docs/superpowers/plans/2026-11-21-finance-profit-dashboard.md``：

* 员工侧分配额只取「绩效工资 + 提成」——``pre_commission_amount`` 已在利润基数里扣过，
  再取一次就是重复扣减。
* 人员成本分摊必须按 ``calculation_version`` 过滤——历史口径行与当前口径行并存时
  同一个人力成本会被算两遍。
* 公司人力成本池已经在各店利润基数里摊派过，月结不得再减一次。
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


def _capture_statements(db):
    statements = []

    async def _execute(statement, *args, **kwargs):
        statements.append(statement)
        return _ScalarResult([])

    db.execute = _execute
    return statements


@pytest.mark.asyncio
async def test_personnel_payload_filters_by_calculation_version():
    """人员成本必须按当前 calculation_version 过滤，否则同月两版行并存时算两遍。"""
    module = _load_service_module()
    service = module.MonthlyProfitSettlementService(_make_db())
    statements = _capture_statements(service.db)

    await service._load_personnel_payload("2026-04")

    assert statements, "应当查询人力成本分摊表"
    where_sql = str(statements[0].whereclause).lower()
    assert "calculation_version" in where_sql, (
        "WHERE 子句必须过滤 calculation_version；"
        f"当前 WHERE = {where_sql}"
    )


@pytest.mark.asyncio
async def test_personnel_payload_returns_shop_breakdown_and_split_amounts():
    """员工侧分配额只取「绩效工资 + 提成」；每店分布只收 shop scope。"""
    module = _load_service_module()
    service = module.MonthlyProfitSettlementService(_make_db())

    class _Row:
        def __init__(self, employee_code, scope, shop_id, performance, commission, pre):
            self.id = f"{employee_code}-alloc"
            self.employee_code = employee_code
            self.allocation_scope = scope
            self.platform_code = "shopee"
            self.shop_id = shop_id
            self.performance_amount = performance
            self.commission_amount = commission
            self.pre_commission_amount = pre

    rows = [
        _Row("E1", "shop", "S1", 1000.0, 2000.0, 5000.0),
        _Row("E2", "company", None, 500.0, 1000.0, 8000.0),
    ]

    async def _execute(statement, *args, **kwargs):
        return _ScalarResult(rows)

    service.db.execute = _execute

    payload = await service._load_personnel_payload("2026-04")

    # 每店分布：只有 shop scope 进 breakdown
    assert payload["shop_breakdown"] == [
        {
            "platform_code": "shopee",
            "shop_id": "S1",
            "performance_amount": 1000.0,
            "commission_amount": 2000.0,
            "allocation_amount": 3000.0,
        }
    ]
    # 总额：全部 scope 的绩效工资 + 提成；pre_commission 已在利润基数扣过，不计
    assert payload["actual_amount"] == 4500.0
    assert payload["performance_salary_amount"] == 1500.0
    assert payload["commission_amount"] == 3000.0


@pytest.mark.asyncio
async def test_net_profit_does_not_deduct_company_pool_again():
    """公司池已在各店利润基数里摊派过，月结不得再减一次。"""
    module = _load_service_module()
    service = module.MonthlyProfitSettlementService(_make_db())

    class _Basis:
        platform_code = "shopee"
        shop_id = "S1"
        basis_version = "SETTLEMENT_BASIS_V1"

        def __init__(self, amount):
            self.profit_basis_amount = amount

    results = [_ScalarResult([_Basis(80000.0)]), _ScalarResult([10000.0])]

    async def _execute(statement, *args, **kwargs):
        return results.pop(0)

    service.db.execute = _execute

    net = await service._load_net_profit_amount("2026-04")

    assert net == 80000.0, "不得再减一次公司池"
