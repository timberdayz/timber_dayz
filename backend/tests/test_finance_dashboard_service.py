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

    await service._load_personnel_payload("2026-04", {})

    assert statements, "应当查询人力成本分摊表"
    where_sql = str(statements[0].whereclause).lower()
    assert "calculation_version" in where_sql, (
        "WHERE 子句必须过滤 calculation_version；" f"当前 WHERE = {where_sql}"
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

    basis_by_shop = {
        ("shopee", "S1"): SimpleNamespace(
            platform_code="shopee", shop_id="S1", profit_basis_amount=80000.0
        )
    }
    payload = await service._load_personnel_payload("2026-04", basis_by_shop)

    # 每店分布：只有 shop scope 进 breakdown
    assert payload["shop_breakdown"] == [
        {
            "platform_code": "shopee",
            "shop_id": "S1",
            "profit_basis_amount": 80000.0,
            "performance_amount": 1000.0,
            "commission_amount": 2000.0,
            "allocation_amount": 3000.0,
            "allocation_ratio": 0.0375,
            "over_allocation_flag": False,
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


def test_summary_has_no_budget_target_or_difference_fields():
    """预算制（目标比例/目标额/差异）与跟投随看板制一起下线。"""
    module = _load_service_module()
    service = module.MonthlyProfitSettlementService(_make_db())

    summary = service.build_summary(
        period_month="2026-04",
        net_profit_amount=100000.0,
        personnel_actual_amount=32000.0,
        adjustment_amount=1000.0,
        status="draft",
    )

    for banned in (
        "personnel_target_ratio",
        "follow_target_ratio",
        "company_target_ratio",
        "personnel_target_amount",
        "follow_target_amount",
        "company_target_amount",
        "difference_amount",
        "difference_ratio",
        "follow_actual_amount",
    ):
        assert banned not in summary, f"{banned} 必须随预算制下线"

    assert summary["company_retained_amount"] == 67000.0
    assert summary["allocation_ratio"] == 0.33
    assert summary["over_allocation_flag"] is False


@pytest.mark.asyncio
async def test_get_dashboard_aggregates_sources_into_flat_payload():
    """看板只做只读聚合：利润基数 + 员工侧分配 + 人工调整 ⇒ 公司留存。"""
    module = _load_service_module()
    service = module.MonthlyProfitSettlementService(_make_db())

    shop_breakdown = [
        {
            "platform_code": "shopee",
            "shop_id": "S1",
            "profit_basis_amount": 100000.0,
            "performance_amount": 1000.0,
            "commission_amount": 2000.0,
            "allocation_amount": 3000.0,
            "allocation_ratio": 0.03,
            "over_allocation_flag": False,
        }
    ]

    async def fake_basis(period_month):
        assert period_month == "2026-04"
        return {
            ("shopee", "S1"): SimpleNamespace(
                platform_code="shopee", shop_id="S1", profit_basis_amount=100000.0
            )
        }

    async def fake_personnel(period_month, basis_by_shop=None):
        assert period_month == "2026-04"
        return {
            "actual_amount": 4500.0,
            "performance_salary_amount": 1500.0,
            "commission_amount": 3000.0,
            "details": [],
            "shop_breakdown": shop_breakdown,
        }

    async def fake_adjustments(period_month):
        assert period_month == "2026-04"
        return [
            {
                "id": 7,
                "adjustment_type": "manual_adjustment",
                "amount": 1000.0,
                "reason": "finance note",
                "created_by": "1",
                "created_at": None,
            }
        ]

    service._load_shop_profit_basis = fake_basis
    service._load_personnel_payload = fake_personnel
    service._load_adjustments_by_month = fake_adjustments

    payload = await service.get_dashboard("2026-04")

    assert payload["period_month"] == "2026-04"
    assert payload["net_profit_amount"] == 100000.0
    assert payload["performance_salary_amount"] == 1500.0
    assert payload["commission_amount"] == 3000.0
    assert payload["employee_allocation_amount"] == 4500.0
    assert payload["manual_adjustment_amount"] == 1000.0
    assert payload["manual_adjustment_count"] == 1
    assert payload["company_retained_amount"] == 94500.0
    assert payload["allocation_ratio"] == 0.055
    assert payload["over_allocation_flag"] is False
    assert payload["shop_breakdown"] == shop_breakdown
    assert payload["adjustments"][0]["id"] == 7
    assert payload["as_of"]


@pytest.mark.asyncio
async def test_shop_breakdown_covers_loss_making_shops_and_excludes_company_scope():
    """每店分布要带利润基数：亏损店也要出现；company scope 不进分布但计入总额。"""
    module = _load_service_module()
    service = module.MonthlyProfitSettlementService(_make_db())

    class _Basis:
        basis_version = "SETTLEMENT_BASIS_V1"

        def __init__(self, platform_code, shop_id, amount):
            self.platform_code = platform_code
            self.shop_id = shop_id
            self.profit_basis_amount = amount

    class _Alloc:
        def __init__(
            self, employee_code, scope, platform_code, shop_id, performance, commission
        ):
            self.id = f"{employee_code}-alloc"
            self.employee_code = employee_code
            self.allocation_scope = scope
            self.platform_code = platform_code
            self.shop_id = shop_id
            self.performance_amount = performance
            self.commission_amount = commission
            self.pre_commission_amount = 0.0

    basis_rows = [
        _Basis("shopee", "S1", 80000.0),
        _Basis("shopee", "S2", -5000.0),
    ]
    allocation_rows = [
        _Alloc("E1", "shop", "shopee", "S1", 1000.0, 2000.0),
        _Alloc("E2", "shop", "shopee", "S2", 300.0, 200.0),
        _Alloc("E3", "company", None, None, 500.0, 500.0),
    ]

    async def _execute(statement, *args, **kwargs):
        sql = str(statement).lower()
        if "shop_profit_basis" in sql:
            return _ScalarResult(basis_rows)
        if "employee_labor_cost_allocations" in sql:
            return _ScalarResult(allocation_rows)
        return _ScalarResult([])

    service.db.execute = _execute

    payload = await service.get_dashboard("2026-04")

    assert payload["net_profit_amount"] == 75000.0

    breakdown = payload["shop_breakdown"]
    assert len(breakdown) == 2, "company scope 不进每店分布"
    by_shop = {item["shop_id"]: item for item in breakdown}

    assert by_shop["S1"] == {
        "platform_code": "shopee",
        "shop_id": "S1",
        "profit_basis_amount": 80000.0,
        "performance_amount": 1000.0,
        "commission_amount": 2000.0,
        "allocation_amount": 3000.0,
        "allocation_ratio": 0.0375,
        "over_allocation_flag": False,
    }
    # 亏损店：占比取 0，但「分过头」仍按金额比判定
    assert by_shop["S2"] == {
        "platform_code": "shopee",
        "shop_id": "S2",
        "profit_basis_amount": -5000.0,
        "performance_amount": 300.0,
        "commission_amount": 200.0,
        "allocation_amount": 500.0,
        "allocation_ratio": 0.0,
        "over_allocation_flag": True,
    }

    # company scope 的行不进分布，但计入员工侧分配总额
    assert payload["employee_allocation_amount"] == 4500.0
    assert payload["performance_salary_amount"] == 1800.0
    assert payload["commission_amount"] == 2700.0

    # 每店利润基数合计必须与净利润对账相等
    assert (
        sum(item["profit_basis_amount"] for item in breakdown)
        == payload["net_profit_amount"]
    )


@pytest.mark.asyncio
async def test_load_adjustments_by_month_joins_settlement_period_month():
    """MonthlyProfitAdjustment 没有 period_month 字段，必须 join 台账主表。"""
    module = _load_service_module()
    service = module.MonthlyProfitSettlementService(_make_db())
    statements = _capture_statements(service.db)

    payload = await service._load_adjustments_by_month("2026-04")

    assert statements, "应当查询人工调整表"
    sql = str(statements[0]).lower()
    assert "join" in sql
    assert "monthly_profit_settlements" in sql
    assert "period_month" in sql
    assert payload == []


@pytest.mark.asyncio
async def test_add_adjustment_requires_reason():
    """调整项必须写明原因，不允许用默认串兜底。"""
    module = _load_service_module()
    service = module.MonthlyProfitSettlementService(_make_db())

    with pytest.raises(ValueError, match="reason"):
        await service.add_adjustment(
            period_month="2026-04",
            adjustment_type="manual_adjustment",
            amount=100.0,
            reason="   ",
        )
