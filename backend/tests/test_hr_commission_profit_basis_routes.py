import asyncio
import importlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _TupleResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


def _load_module():
    return importlib.import_module("backend.routers.hr_commission")


def _body(resp):
    return json.loads(resp.body.decode("utf-8"))


def test_shop_profit_statistics_uses_profit_basis_amount_for_person_income():
    module = _load_module()
    domain_module = module.domain_module
    db = AsyncMock()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    current_user = SimpleNamespace(user_id=1)

    shop_row = SimpleNamespace(
        platform="shopee",
        store_name="Shop A",
        platform_shop_id="s1",
        shop_account_id="s1",
        shop_id="s1",
        account_id="s1",
        enabled=True,
    )
    config_row = SimpleNamespace(platform_code="shopee", shop_id="s1", allocatable_profit_rate=0.8)
    assign_row = SimpleNamespace(
        employee_code="E001",
        platform_code="shopee",
        shop_id="s1",
        commission_ratio=0.1,
        role="supervisor",
        status="active",
        year_month="2026-04",
    )

    db.execute = AsyncMock(
        side_effect=[
            _ScalarResult([shop_row]),
            _ScalarResult([config_row]),
            _ScalarResult([]),
            _ScalarResult([assign_row]),
        ]
    )
    domain_module.load_shop_monthly_metrics = AsyncMock(
        return_value={
            "shopee|s1": {
                "monthly_sales": 10000.0,
                "monthly_profit": 2000.0,
                "achievement_rate": 80.0,
            }
        }
    )

    class _FakeProfitBasisService:
        def __init__(self, db):
            self.db = db

        async def build_profit_basis(self, year_month, platform_code, shop_id, basis_version="A_ONLY_V1"):
            return {
                "period_month": year_month,
                "platform_code": platform_code,
                "shop_id": shop_id,
                "orders_profit_amount": 2000.0,
                "a_class_cost_amount": 500.0,
                "profit_basis_amount": 1500.0,
                "basis_version": basis_version,
            }

    domain_module.ProfitBasisService = _FakeProfitBasisService

    resp = asyncio.run(
        domain_module.get_shop_profit_statistics(
            request=request,
            month="2026-04",
            db=db,
            current_user=current_user,
        )
    )

    body = _body(resp)
    row = body["data"][0]
    assert row["monthly_profit"] == 2000.0
    assert row["profit_basis_amount"] == 1500.0
    assert row["a_class_cost_amount"] == 500.0
    assert row["allocatable_profit_amount"] == 1200.0
    assert row["estimated_total_commission"] == 120.0
    assert row["supervisor_profit"] == 120.0
    assert row["operator_profit"] == 0


def test_shop_profit_statistics_floors_negative_profit_basis_for_estimated_commission():
    module = _load_module()
    domain_module = module.domain_module
    db = AsyncMock()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    current_user = SimpleNamespace(user_id=1)

    shop_row = SimpleNamespace(
        platform="shopee",
        store_name="Shop Negative",
        platform_shop_id="s_neg",
        shop_account_id="s_neg",
        shop_id="s_neg",
        account_id="s_neg",
        enabled=True,
    )
    config_row = SimpleNamespace(platform_code="shopee", shop_id="s_neg", allocatable_profit_rate=0.25)
    assign_row = SimpleNamespace(
        employee_code="E_NEG",
        platform_code="shopee",
        shop_id="s_neg",
        commission_ratio=0.25,
        role="supervisor",
        status="active",
        year_month="2026-04",
    )

    db.execute = AsyncMock(
        side_effect=[
            _ScalarResult([shop_row]),
            _ScalarResult([config_row]),
            _ScalarResult([]),
            _ScalarResult([assign_row]),
        ]
    )
    domain_module.load_shop_monthly_metrics = AsyncMock(
        return_value={
            "shopee|s_neg": {
                "monthly_sales": 1000.0,
                "monthly_profit": -1000.0,
                "achievement_rate": 80.0,
            }
        }
    )

    class _FakeProfitBasisService:
        def __init__(self, db):
            self.db = db

        async def build_profit_basis(self, year_month, platform_code, shop_id, basis_version="A_ONLY_V1"):
            return {
                "period_month": year_month,
                "platform_code": platform_code,
                "shop_id": shop_id,
                "orders_profit_amount": -1000.0,
                "a_class_cost_amount": 0.0,
                "profit_basis_amount": -1000.0,
                "basis_version": basis_version,
            }

    domain_module.ProfitBasisService = _FakeProfitBasisService

    resp = asyncio.run(
        domain_module.get_shop_profit_statistics(
            request=request,
            month="2026-04",
            db=db,
            current_user=current_user,
        )
    )

    row = _body(resp)["data"][0]
    assert row["profit_basis_amount"] == -1000.0
    assert row["allocatable_profit_amount"] == 0.0
    assert row["estimated_total_commission"] == 0.0
    assert row["supervisor_profit"] == 0.0


def test_load_profit_basis_map_rebuilds_unlocked_snapshot_for_statistics():
    module = _load_module()
    domain_module = module.domain_module
    db = AsyncMock()
    snapshot_row = SimpleNamespace(
        period_month="2026-04",
        platform_code="shopee",
        shop_id="s1",
        orders_profit_amount=2000.0,
        a_class_cost_amount=0.0,
        profit_basis_amount=0.0,
        is_locked=False,
    )

    db.execute = AsyncMock(return_value=_ScalarResult([snapshot_row]))

    class _FakeProfitBasisService:
        def __init__(self, db):
            self.db = db

        async def build_profit_basis(self, year_month, platform_code, shop_id, basis_version="A_ONLY_V1"):
            return {
                "period_month": year_month,
                "platform_code": platform_code,
                "shop_id": shop_id,
                "orders_profit_amount": 2000.0,
                "a_class_cost_amount": 500.0,
                "profit_basis_amount": 1500.0,
                "basis_version": basis_version,
            }

    domain_module.ProfitBasisService = _FakeProfitBasisService

    result = asyncio.run(
        domain_module._load_profit_basis_map(
            db,
            "2026-04",
            [{"platform_code": "shopee", "shop_id": "s1"}],
        )
    )

    assert result["shopee|s1"]["orders_profit_amount"] == 2000.0
    assert result["shopee|s1"]["a_class_cost_amount"] == 500.0
    assert result["shopee|s1"]["profit_basis_amount"] == 1500.0


def test_list_employee_performance_reads_english_columns():
    module = _load_module()
    db = AsyncMock()
    perf = SimpleNamespace(
        id=1,
        employee_code="EMP001",
        year_month="2025-01",
        actual_sales=1000.0,
        achievement_rate=0.8,
        performance_score=88.0,
        calculated_at="2025-01-31T00:00:00",
    )

    async def _execute(stmt, params=None):
        return _ScalarResult([perf])

    db.execute = AsyncMock(side_effect=_execute)

    resp = asyncio.run(
        module.list_employee_performance(
            employee_code=None,
            year_month="2025-01",
            page=1,
            page_size=20,
            db=db,
        )
    )

    assert len(resp) == 1
    assert resp[0].employee_code == "EMP001"
    assert float(resp[0].actual_sales) == 1000.0
    assert float(resp[0].performance_score) == 88.0


def test_list_employee_commissions_reads_english_columns():
    module = _load_module()
    db = AsyncMock()
    comm = SimpleNamespace(
        id=2,
        employee_code="EMP002",
        year_month="2025-01",
        sales_amount=2000.0,
        commission_amount=300.0,
        commission_rate=0.15,
        calculated_at="2025-01-31T00:00:00",
    )

    async def _execute(stmt, params=None):
        return _ScalarResult([comm])

    db.execute = AsyncMock(side_effect=_execute)

    resp = asyncio.run(
        module.list_employee_commissions(
            employee_code=None,
            year_month="2025-01",
            page=1,
            page_size=20,
            db=db,
        )
    )

    assert len(resp) == 1
    assert resp[0].employee_code == "EMP002"
    assert float(resp[0].sales_amount) == 2000.0
    assert float(resp[0].commission_amount) == 300.0
