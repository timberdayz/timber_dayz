"""
config_management 销售目标 CRUD 测试（第三批-C 口径）

第三批-C：``a_class.sales_targets_a`` 已下线，新增/更新改为直接写
真 SSOT ``a_class.target_breakdown``（``breakdown_type='shop'`` 的
「店铺 × 月」档位），并在写完后**重算父目标的公司级合计**。
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
    """同时支持 scalars()/mappings()/fetch* 几种取数风格。"""

    def __init__(self, row=None, rows=None):
        self._row = row
        if rows is not None:
            self._rows = list(rows)
        else:
            self._rows = [row] if row is not None else []

    def scalars(self):
        return self

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one(self):
        return self._rows[0]

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows

    def rowcount(self):
        return len(self._rows)


def test_create_sales_target_writes_target_breakdown_ssot():
    db = AsyncMock()
    row = (42, "S1", "2026-03", 1000.0, 10, datetime.now(timezone.utc))
    # 依次: 反查平台 -> 找已有档位行(无) -> 找月度父目标 -> 写档位行
    #       -> 重算父目标合计 -> 回读
    db.execute = AsyncMock(
        side_effect=[
            _MockResult(rows=["shopee"]),
            _MockResult(),
            _MockResult(rows=[7]),
            _MockResult(rows=[42]),
            _MockResult(),
            _MockResult(row=row),
        ]
    )
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

    assert result.id == 42
    assert result.shop_id == "S1"
    assert result.year_month == "2026-03"
    assert result.target_sales_amount == 1000.0
    assert result.target_order_count == 10
    assert db.commit.await_count == 1
    # 不再有「英文列失败 → 中文列回退」：一次跑通，不需要 rollback
    assert db.rollback.await_count == 0

    statements = [str(call.args[0]) for call in db.execute.await_args_list]
    assert "core.dim_shops" in statements[0]
    assert "a_class.target_breakdown" in statements[1]
    assert "a_class.sales_targets" in statements[2]
    assert "INSERT INTO a_class.target_breakdown" in statements[3]
    assert "a_class.sales_targets_a" not in "".join(statements)


def test_update_sales_target_updates_target_breakdown_ssot():
    db = AsyncMock()
    row = (12, "S2", "2026-03", 2000.0, 20, datetime.now(timezone.utc))
    # 依次: UPDATE ... RETURNING target_id -> 重算父目标合计 -> 回读
    db.execute = AsyncMock(
        side_effect=[
            _MockResult(rows=[7]),
            _MockResult(),
            _MockResult(row=row),
        ]
    )
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
    assert result.target_sales_amount == 2000.0
    assert db.commit.await_count == 1

    statements = [str(call.args[0]) for call in db.execute.await_args_list]
    assert "UPDATE a_class.target_breakdown" in statements[0]
    assert "target_amount = :target_sales_amount" in statements[0]
    assert "target_quantity = :target_order_count" in statements[0]
    assert "a_class.sales_targets_a" not in "".join(statements)
