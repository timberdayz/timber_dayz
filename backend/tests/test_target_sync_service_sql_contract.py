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


def test_target_sync_service_no_longer_touches_dropped_sales_targets_a():
    """第三批-C：``a_class.sales_targets_a`` 已下线，服务里不能再读写它。"""
    source = Path("backend/services/target_sync_service.py").read_text(encoding="utf-8")

    # 不再 import 已退役的 ORM 模型
    assert "SalesTargetA" not in source
    # 不再对已删表做投影写入（文档字符串里可以解释历史，但 SQL 里不能有）
    assert "FROM a_class.sales_targets_a" not in source
    assert "INTO a_class.sales_targets_a" not in source
    assert "INSERT INTO" not in source
    assert "DELETE FROM" not in source
    assert "ON CONFLICT" not in source


def test_target_sync_service_reads_target_breakdown_as_ssot():
    source = Path("backend/services/target_sync_service.py").read_text(encoding="utf-8")

    assert "TargetBreakdown" in source
    assert 'TargetBreakdown.breakdown_type == "shop"' in source
    assert "select_effective_shop_breakdowns" in source


def test_target_sync_service_avoids_asyncpg_named_param_cast_syntax():
    source = Path("backend/services/target_sync_service.py").read_text(encoding="utf-8")

    assert ":period_start::date" not in source
    assert "CAST(:period_start AS date)" not in source


def test_target_sync_service_prefers_period_scoped_shop_rows():
    """有效店铺档位 = 周期内行优先，没有周期内行才回退到历史无周期行。"""
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

    result = asyncio.run(service.sync_target_to_a_class(5, commit=False))

    # 周期内行优先 ⇒ 只有 1 行生效（与旧版 upsert 计数口径一致）
    assert result["synced"] == 1
    assert result["skipped"] == 0
    assert result["errors"] == []
    # 只读两次：读目标 + 读分解，不再有任何投影写入
    assert db.execute.await_count == 2


def test_target_sync_service_delete_does_not_remove_ssot_rows():
    """删除目标时**不能**主动删分解行 —— 那是 SSOT 本体，由外键级联清理。"""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarsResult([]))

    service = TargetSyncService(db)

    result = asyncio.run(service.delete_target_from_a_class(5, commit=False))

    assert result["deleted"] == 0
    assert result["errors"] == []
    # 只做一次只读核对
    assert db.execute.await_count == 1
    statement = str(db.execute.await_args.args[0])
    assert "SELECT" in statement.upper()
    assert "DELETE" not in statement.upper()
