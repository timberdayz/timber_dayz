import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from backend.routers.target_management import create_target, list_target_products, update_target
from backend.schemas.target import TargetCreateRequest, TargetUpdateRequest


class _ScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _ScalarOneResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


def test_create_target_accepts_profit_and_operation_fields():
    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    async def _refresh(target):
        target.id = 101
        target.achieved_amount = 0.0
        target.achieved_quantity = 0
        target.achievement_rate = 0.0
        target.created_at = datetime.now(timezone.utc)
        target.updated_at = datetime.now(timezone.utc)

    db.refresh = AsyncMock(side_effect=_refresh)
    db.execute = AsyncMock(return_value=_ScalarsResult([]))

    request = TargetCreateRequest(
        target_name="2026-04 运营目标",
        target_type="operation",
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        target_amount=0.0,
        target_quantity=0,
        target_profit_amount=0.0,
        metric_code="customer_satisfaction",
        metric_name="客户满意度",
        metric_direction="higher_better",
        target_value=95.0,
        max_score=20.0,
        penalty_enabled=False,
        manual_score_enabled=False,
    )

    result = asyncio.run(
        create_target(
            request=request,
            db=db,
            current_user=SimpleNamespace(username="admin"),
        )
    )

    assert result["success"] is True
    assert result["data"]["target_profit_amount"] == 0.0
    assert result["data"]["metric_code"] == "customer_satisfaction"
    assert result["data"]["metric_direction"] == "higher_better"
    assert result["data"]["target_value"] == 95.0
    assert result["data"]["max_score"] == 20.0


def test_update_target_accepts_profit_goal_fields():
    db = AsyncMock()
    target = SimpleNamespace(
        id=5,
        target_name="2026-04 月度目标",
        target_type="shop",
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        target_amount=10000.0,
        target_quantity=100,
        target_profit_amount=1500.0,
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

    db.execute = AsyncMock(return_value=_ScalarOneResult(target))
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    request = TargetUpdateRequest(
        target_profit_amount=3000.0,
        achieved_profit_amount=1200.0,
    )

    result = asyncio.run(
        update_target(
            target_id=5,
            request=request,
            db=db,
            current_user=SimpleNamespace(username="admin"),
        )
    )

    assert result["success"] is True
    assert result["data"]["target_profit_amount"] == 3000.0
    assert result["data"]["achieved_profit_amount"] == 1200.0


def test_create_product_target_accepts_product_identity_fields():
    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    async def _refresh(target):
        target.id = 102
        target.achieved_amount = 0.0
        target.achieved_quantity = 0
        target.achievement_rate = 0.0
        target.created_at = datetime.now(timezone.utc)
        target.updated_at = datetime.now(timezone.utc)

    db.refresh = AsyncMock(side_effect=_refresh)
    db.execute = AsyncMock(return_value=_ScalarsResult([]))

    request = TargetCreateRequest(
        target_name="2026-04 重点产品目标",
        target_type="product",
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        target_amount=500.0,
        target_quantity=20,
        target_profit_amount=100.0,
        product_id=88,
        platform_sku="sku-88",
        company_sku="cmp-88",
    )

    result = asyncio.run(
        create_target(
            request=request,
            db=db,
            current_user=SimpleNamespace(username="admin"),
        )
    )

    assert result["success"] is True
    assert result["data"]["product_id"] == 88
    assert result["data"]["platform_sku"] == "sku-88"
    assert result["data"]["company_sku"] == "cmp-88"


def test_list_target_products_returns_product_candidates():
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=_RowsResult(
            [
                (
                    "shopee",
                    "shop-1",
                    "sku-88",
                    "Product 88",
                    88,
                    "cmp-88",
                )
            ]
        )
    )

    result = asyncio.run(
        list_target_products(
            keyword="sku-88",
            limit=20,
            db=db,
            current_user=SimpleNamespace(username="admin"),
        )
    )

    assert result["success"] is True
    assert result["data"][0]["platform_sku"] == "sku-88"
    assert result["data"][0]["product_id"] == 88
    assert result["data"][0]["company_sku"] == "cmp-88"
