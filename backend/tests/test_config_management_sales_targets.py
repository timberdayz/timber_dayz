"""
config_management 销售目标接口测试（第三批-C 口径）

第三批-C：``a_class.sales_targets_a``（派生副本）已下线，接口改为直接读写
真 SSOT ``a_class.target_breakdown``（``breakdown_type='shop'`` 的
「店铺 × 月」档位）+ 其父目标 ``a_class.sales_targets``。

这里断言的是**新契约**：
- 列表：直接查 ``a_class.target_breakdown``（不再有「英文列失败 → 中文列回退」双分支）；
- 新增：先反查平台（``core.dim_shops``）→ 找已有档位行 → 没有就挂到（必要时新建的）
  月度父目标下 → 写 ``a_class.target_breakdown`` → 重算父目标合计。
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from backend.routers.config_management import list_sales_targets


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


def test_list_sales_targets_reads_target_breakdown_ssot():
    db = AsyncMock()
    row = (1, "S1", "2026-03", 1000.0, 10, datetime.now(timezone.utc))
    db.execute = AsyncMock(return_value=_MockResult(row))

    result = asyncio.run(list_sales_targets(shop_id=None, year_month="2026-03", db=db))

    assert len(result) == 1
    assert result[0].id == 1
    assert result[0].shop_id == "S1"
    assert result[0].year_month == "2026-03"
    assert result[0].target_sales_amount == 1000.0
    assert result[0].target_order_count == 10

    # 直读真 SSOT，不再有「英文列失败 → 中文列回退」双分支
    assert db.execute.await_count == 1
    statement = str(db.execute.await_args.args[0])
    assert "a_class.target_breakdown" in statement
    assert "breakdown_type = 'shop'" in statement
    assert "a_class.sales_targets_a" not in statement
    # 单次查询即可成功 ⇒ 不需要 rollback 回退
    assert db.rollback.await_count == 0


def test_list_sales_targets_reads_month_key_from_period_label():
    db = AsyncMock()
    row = (2, "S2", "2026-04", 2000.0, 20, datetime.now(timezone.utc))
    db.execute = AsyncMock(return_value=_MockResult(row))

    result = asyncio.run(list_sales_targets(shop_id=None, year_month=None, db=db))

    assert result[0].year_month == "2026-04"
    statement = str(db.execute.await_args.args[0])
    # 月份键来自 target_breakdown.period_label（仓库既有的「店铺月度档位」约定）
    assert "period_label" in statement
