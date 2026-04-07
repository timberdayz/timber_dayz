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
    module.load_shop_monthly_metrics = AsyncMock(
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
                "profit_basis_amount": 1500.0,
                "basis_version": basis_version,
            }

    module.ProfitBasisService = _FakeProfitBasisService

    resp = asyncio.run(
        module.get_shop_profit_statistics(
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
    assert row["supervisor_profit"] == 120.0
    assert row["operator_profit"] == 0
