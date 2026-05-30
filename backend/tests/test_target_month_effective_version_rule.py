import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.routers.target_management import get_target_by_month


class _ScalarOneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _ScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


def test_target_by_month_uses_latest_active_target_version():
    db = AsyncMock()
    newer = SimpleNamespace(
        id=9,
        target_name="2026-03 最新店铺目标",
        target_type="shop",
        scope_type=None,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        target_amount=1000.0,
        target_quantity=0,
        target_profit_amount=200.0,
        achieved_amount=0.0,
        achieved_quantity=0,
        achieved_profit_amount=0.0,
        achievement_rate=0.0,
        status="active",
        description=None,
        weekday_ratios=None,
        created_by="admin",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        metric_code=None,
        metric_name=None,
        metric_direction=None,
        target_value=None,
        achieved_value=None,
        max_score=None,
        penalty_enabled=False,
        penalty_threshold=None,
        penalty_per_unit=None,
        penalty_max=None,
        manual_score_enabled=False,
        manual_score_value=None,
    )
    breakdown = SimpleNamespace(
        id=1,
        target_id=9,
        breakdown_type="shop",
        platform_code="shopee",
        shop_id="shop-1",
        period_start=None,
        period_end=None,
        period_label=None,
        target_amount=1000.0,
        target_quantity=0,
        target_profit_amount=200.0,
        achieved_amount=0.0,
        achieved_quantity=0,
        achieved_profit_amount=0.0,
        achievement_rate=0.0,
        product_id=None,
        platform_sku=None,
        company_sku=None,
        target_value=None,
        achieved_value=None,
        manual_score_value=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    dim_shop = SimpleNamespace(shop_name="Shop 1")

    execute_calls = {"n": 0}

    async def _execute(_stmt, *args, **kwargs):
        execute_calls["n"] += 1
        n = execute_calls["n"]
        if n == 1:
            return _ScalarOneResult(newer)
        if n == 2:
            return _ScalarsResult([breakdown])
        if n == 3:
            return _ScalarOneResult(dim_shop)
        raise AssertionError(f"unexpected execute call #{n}")

    db.execute = AsyncMock(side_effect=_execute)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    current_user = SimpleNamespace(user_id=1)

    resp = asyncio.run(
        get_target_by_month(
            request=request,
            month="2026-03",
            target_type="shop",
            db=db,
            current_user=current_user,
        )
    )

    body = resp.body.decode("utf-8")
    assert "2026-03 最新店铺目标" in body
