import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.schemas.target import ShopTargetWorkbenchApplyRequest, ShopTargetWorkbenchShopInput
from backend.services.shop_target_workbench_service import ShopTargetWorkbenchService


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


def test_shop_workbench_response_includes_standard_name_alias_and_shop_id():
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarsResult([]),
            _ScalarsResult(
                [
                    SimpleNamespace(
                        id=1,
                        platform="shopee",
                        platform_shop_id="SHP-1",
                        shop_account_id="acct-1",
                        store_name="Standard Shop",
                        enabled=True,
                    )
                ]
            ),
            _ScalarsResult([SimpleNamespace(alias_value="standard-shop", is_primary=True)]),
            _ScalarsResult([]),
        ]
    )

    service = ShopTargetWorkbenchService(db)
    result = asyncio.run(service.get_workbench("2026-03"))

    assert result.year_month == "2026-03"
    assert result.shops[0].platform_code == "shopee"
    assert result.shops[0].shop_id == "SHP-1"
    assert result.shops[0].standard_name == "Standard Shop"
    assert "standard-shop" in result.shops[0].aliases
    shop_query = db.execute.await_args_list[1].args[0]
    assert "shop_accounts" in str(shop_query)
    assert "enabled" in str(shop_query)


def test_apply_shop_workbench_creates_shop_and_daily_breakdowns_then_syncs_projection():
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_ScalarsResult([]), None])
    db.add = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    async def _flush_assign_id():
        for call in db.add.call_args_list:
            target = call.args[0]
            if hasattr(target, "target_name") and not getattr(target, "id", None):
                target.id = 77

    db.flush.side_effect = _flush_assign_id

    service = ShopTargetWorkbenchService(db)
    service.cleanup_projection = AsyncMock(return_value={"deleted": 0, "errors": []})
    service.sync_projection = AsyncMock(return_value={"synced": 1, "errors": []})

    request = ShopTargetWorkbenchApplyRequest(
        year_month="2026-03",
        company_target_amount=243148.08,
        company_target_quantity=2655,
        weekday_ratios={"1": 0.2, "2": 0.2, "3": 0.2, "4": 0.2, "5": 0.1, "6": 0.05, "7": 0.05},
        shops=[
            ShopTargetWorkbenchShopInput(
                platform_code="shopee",
                shop_id="SHP-1",
                ratio=1.0,
                target_amount=243148.08,
                target_quantity=2655,
            )
        ],
    )

    result = asyncio.run(service.apply(request, username="admin"))

    added_objects = [call.args[0] for call in db.add.call_args_list]
    breakdown_types = [getattr(obj, "breakdown_type", None) for obj in added_objects]

    assert result.target_id == 77
    target = next(obj for obj in [call.args[0] for call in db.add.call_args_list] if hasattr(obj, "target_name"))
    assert round(sum(target.weekday_ratios.values()), 6) == 1
    assert "shop" in breakdown_types
    assert "time" in breakdown_types
    assert "shop_time" in breakdown_types
    assert service.cleanup_projection.await_count == 1
    assert service.sync_projection.await_count == 1
    assert db.commit.await_count == 1


def test_find_month_target_uses_latest_updated_record_when_month_has_multiple_versions():
    older = SimpleNamespace(id=1, updated_at=datetime(2026, 3, 1, tzinfo=timezone.utc))
    latest = SimpleNamespace(id=2, updated_at=datetime(2026, 3, 15, tzinfo=timezone.utc))
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarsResult([latest, older]))

    service = ShopTargetWorkbenchService(db)
    result = asyncio.run(service._find_month_target(date(2026, 3, 1), date(2026, 3, 31)))

    assert result.id == 2
    query_text = str(db.execute.await_args.args[0])
    assert "updated_at" in query_text


def test_deactivate_older_month_targets_keeps_latest_month_version_only():
    current = SimpleNamespace(id=9, status="active")
    older = SimpleNamespace(id=8, status="active")
    db = AsyncMock()
    service = ShopTargetWorkbenchService(db)
    service.cleanup_projection = AsyncMock(return_value={"deleted": 1, "errors": []})

    asyncio.run(service._deactivate_older_month_targets([current, older], current.id))

    assert current.status == "active"
    assert older.status == "inactive"
    service.cleanup_projection.assert_awaited_once_with(older.id)
