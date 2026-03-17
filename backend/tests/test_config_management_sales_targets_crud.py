"""
config_management 销售目标 CRUD 回退逻辑测试
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from backend.routers.config_management import (
    SalesTargetCreate,
    SalesTargetUpdate,
    create_sales_target,
    update_sales_target,
)


class _MockResult:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row


def test_create_sales_target_fallback_select_after_commit():
    db = AsyncMock()
    row = (11, "S1", "2026-03", 1000.0, 10, datetime.now(timezone.utc))
    # 依次: 英文INSERT成功 -> 英文SELECT失败 -> 中文SELECT成功
    db.execute = AsyncMock(side_effect=[None, Exception("no english columns"), _MockResult(row)])
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    result = asyncio.run(
        create_sales_target(
            SalesTargetCreate(
                shop_id="S1",
                year_month="2026-03",
                target_sales_amount=1000.0,
                target_order_count=10,
            ),
            db=db,
        )
    )

    assert result.id == 11
    assert result.shop_id == "S1"
    assert db.commit.await_count == 1
    assert db.rollback.await_count >= 1


def test_update_sales_target_fallback_select_after_commit():
    db = AsyncMock()
    row = (12, "S2", "2026-03", 2000.0, 20, datetime.now(timezone.utc))
    # 依次: UPDATE成功 -> 英文SELECT失败 -> 中文SELECT成功
    db.execute = AsyncMock(side_effect=[None, Exception("no english columns"), _MockResult(row)])
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    result = asyncio.run(
        update_sales_target(
            12,
            SalesTargetUpdate(target_sales_amount=2000.0, target_order_count=20),
            db=db,
        )
    )

    assert result.id == 12
    assert result.shop_id == "S2"
    assert db.commit.await_count == 1
    assert db.rollback.await_count >= 1
