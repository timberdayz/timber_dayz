import asyncio
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services.target_sync_service import TargetSyncService


class _ScalarOneResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _ScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


def test_target_sync_service_avoids_asyncpg_named_param_cast_syntax():
    source = Path("backend/services/target_sync_service.py").read_text(encoding="utf-8")

    assert ":period_start::date" not in source
    assert "CAST(:period_start AS date)" in source


def test_target_sync_service_uses_platform_shop_month_identity():
    source = Path("backend/services/target_sync_service.py").read_text(encoding="utf-8")

    assert "platform_code=platform_code" in source
    assert "platform_code: str" in source
    assert "ON CONFLICT (platform_code," in source
    assert "platform_code = :platform_code" in source


def test_target_sync_service_prefers_period_scoped_shop_rows():
    db = AsyncMock()
    target = SimpleNamespace(
        id=5,
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
    )
    scoped_shop = SimpleNamespace(
        target_id=5,
        breakdown_type="shop",
        platform_code="tiktok",
        shop_id="shop-1",
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        target_amount=126480.0,
        target_quantity=959,
    )
    legacy_shop = SimpleNamespace(
        target_id=5,
        breakdown_type="shop",
        platform_code="tiktok",
        shop_id="shop-1",
        period_start=None,
        period_end=None,
        target_amount=252960.0,
        target_quantity=1918,
    )
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneResult(target),
            _ScalarsResult([scoped_shop, legacy_shop]),
        ]
    )

    service = TargetSyncService(db)
    service._upsert_sales_target_a = AsyncMock()

    result = asyncio.run(service.sync_target_to_a_class(5, commit=False))

    assert result["synced"] == 1
    service._upsert_sales_target_a.assert_awaited_once()
    kwargs = service._upsert_sales_target_a.await_args.kwargs
    assert kwargs["platform_code"] == "tiktok"
    assert kwargs["shop_id"] == "shop-1"
    assert kwargs["target_sales_amount"] == 126480.0
    assert kwargs["target_quantity"] == 959
