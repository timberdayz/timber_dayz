"""
config_management 销售目标接口回退逻辑测试
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from backend.routers.config_management import list_sales_targets


class _MockResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


def test_list_sales_targets_fallback_after_rollback():
    db = AsyncMock()
    row = (1, "S1", "2026-03", 1000.0, 10, datetime.now(timezone.utc))
    db.execute = AsyncMock(side_effect=[Exception("english columns failed"), _MockResult([row])])
    db.rollback = AsyncMock()

    result = asyncio.run(list_sales_targets(shop_id=None, year_month="2026-03", db=db))

    assert len(result) == 1
    assert result[0].shop_id == "S1"
    assert db.rollback.await_count >= 1
