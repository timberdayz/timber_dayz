import json
from unittest.mock import AsyncMock

import pytest

from backend.routers.inventory_management import get_products


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _PlatformTableManager:
    def get_table_name(self, **_kwargs):
        return "stub_inventory_table"


@pytest.mark.asyncio
async def test_get_products_returns_empty_paginated_payload_without_sync_execute_usage(
    monkeypatch,
):
    db = AsyncMock()
    db.execute.side_effect = [
        _ScalarResult(True),
        _ScalarResult(0),
        _RowsResult([]),
    ]

    monkeypatch.setattr(
        "backend.services.platform_table_manager.get_platform_table_manager",
        lambda _db: _PlatformTableManager(),
    )

    response = await get_products(
        platform="shopee",
        keyword=None,
        category=None,
        low_stock=None,
        page=1,
        page_size=20,
        db=db,
    )
    payload = json.loads(response.body)

    assert payload["success"] is True
    assert payload["data"]["data"] == []
    assert payload["data"]["total"] == 0
    assert payload["data"]["performance"]["query_time_ms"] >= 0
    assert db.execute.await_count == 3
