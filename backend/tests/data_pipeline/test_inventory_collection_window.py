"""增量采集窗口计算（水位线 + 断档补采）的行为测试。

关键门禁：
1. 用户显式配置的区间**原样使用**（不裁剪、不回填）；
2. 自动推进从水位线接续，并保留重叠余量；
3. 断档触发长窗口补采；
4. 上一批失败 → 窗口覆盖失败期；
5. 取数只打 `mart.inventory_state` 与 `core.collection_config_runs`，
   不碰 raw_data / 订单域。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.services.inventory.inventory_collection_window_service import (
    REASON_CUSTOM,
    REASON_FAILED_BACKFILL,
    REASON_FIRST_RUN,
    REASON_GAP_BACKFILL,
    REASON_WATERMARK,
    CollectionWindow,
    compute_collection_window,
    load_collection_watermark,
    load_last_failed_run_start,
)

NOW = datetime(2026, 10, 25, 9, 0, tzinfo=timezone.utc)


def _days_ago(days: int) -> datetime:
    return NOW - timedelta(days=days)


# ----------------------------------------------------------------------
# 窗口计算（纯函数）
# ----------------------------------------------------------------------


def test_explicit_custom_range_is_used_verbatim():
    """用户显式指定区间 → 原样返回，不被水位线裁剪。"""
    start = _days_ago(3)
    end = _days_ago(1)

    window = compute_collection_window(
        now=NOW,
        watermark=_days_ago(30),
        requested_start=start,
        requested_end=end,
    )

    assert window.start == start
    assert window.end == end
    assert window.reason == REASON_CUSTOM
    assert window.is_custom is True


def test_custom_range_is_not_backfilled_even_when_a_batch_failed():
    """custom 是「我就是要采这一段」：失败期回填不适用于它。"""
    window = compute_collection_window(
        now=NOW,
        requested_start=_days_ago(2),
        requested_end=NOW,
        last_failed_start=_days_ago(10),
    )

    assert window.start == _days_ago(2)
    assert window.reason == REASON_CUSTOM
    assert REASON_FAILED_BACKFILL not in window.reasons


def test_auto_window_continues_from_the_watermark_with_overlap():
    """自动推进：从水位线接着采，并往前留 1 天重叠余量。"""
    watermark = _days_ago(1)

    window = compute_collection_window(now=NOW, watermark=watermark)

    assert window.start == watermark - timedelta(days=1)
    assert window.end == NOW
    assert window.reason == REASON_WATERMARK
    assert window.gap_days == 1


def test_first_run_without_watermark_falls_back_to_a_long_window():
    """从没采过 → 没有水位线可接，先铺一段长窗口。"""
    window = compute_collection_window(now=NOW, watermark=None)

    assert window.start == NOW - timedelta(days=7)
    assert window.reason == REASON_FIRST_RUN


def test_gap_triggers_long_window_backfill():
    """断档（距今超过阈值）→ 窗口至少覆盖最近的长窗口天数。

    断档越久，水位线的精度越不可信（妙手时间戳会被 bulk UPDATE 戳穿、
    两侧时钟有偏差）→ 宁可多采（重复采由落盘 upsert 幂等吃掉），不可漏采。
    """
    watermark = _days_ago(5)

    window = compute_collection_window(now=NOW, watermark=watermark)

    assert window.start == NOW - timedelta(days=7)
    assert window.reason == REASON_GAP_BACKFILL
    assert window.gap_days == 5


def test_gap_backfill_never_narrows_an_already_long_window():
    """水位线比长窗口更久 → 以水位线为准，**绝不能把窗口收窄**。

    收窄 = 跳过中间那几天 = 静默漏采，是这个模块最不能犯的错。
    """
    watermark = _days_ago(30)

    window = compute_collection_window(now=NOW, watermark=watermark)

    assert window.start == watermark - timedelta(days=1)
    assert window.reason == REASON_WATERMARK
    assert window.gap_days == 30


def test_gap_backfill_never_moves_the_start_forward():
    """断档但长窗口仍比水位线晚 → 不许把起点往后推（否则会跳过中间那几天）。"""
    watermark = _days_ago(2)

    window = compute_collection_window(now=NOW, watermark=watermark)

    assert window.start == watermark - timedelta(days=1)
    assert REASON_GAP_BACKFILL not in window.reasons


def test_failed_batch_window_is_covered():
    """上一批失败 → 窗口必须覆盖失败期。"""
    watermark = _days_ago(1)
    failed_start = _days_ago(6)

    window = compute_collection_window(
        now=NOW,
        watermark=watermark,
        last_failed_start=failed_start,
    )

    assert window.start == failed_start - timedelta(days=1)
    assert window.reason == REASON_FAILED_BACKFILL
    assert REASON_FAILED_BACKFILL in window.reasons


def test_failed_backfill_only_applies_when_it_would_widen_the_window():
    """失败期已经在窗口内 → 不重复回填。"""
    watermark = _days_ago(10)

    window = compute_collection_window(
        now=NOW,
        watermark=watermark,
        last_failed_start=_days_ago(1),
    )

    assert REASON_FAILED_BACKFILL not in window.reasons


def test_window_reports_every_reason_it_applied():
    """断档 + 失败期同时成立 → 两个成因都要记录，便于运维排查。"""
    window = compute_collection_window(
        now=NOW,
        watermark=_days_ago(5),
        last_failed_start=_days_ago(20),
    )

    assert REASON_WATERMARK in window.reasons
    assert REASON_GAP_BACKFILL in window.reasons
    assert REASON_FAILED_BACKFILL in window.reasons


def test_window_is_a_frozen_value_object():
    window = CollectionWindow(start=NOW, end=NOW, reason=REASON_CUSTOM)
    with pytest.raises(Exception):
        window.start = NOW  # type: ignore[misc]


# ----------------------------------------------------------------------
# 取数
# ----------------------------------------------------------------------


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _FakeSession:
    """只记录 SQL 与参数的假 session。"""

    def __init__(self, results):
        self._results = list(results)
        self.executed: list[tuple[str, dict]] = []

    async def execute(self, statement, params=None):
        text = str(statement)
        self.executed.append((text, dict(params or {})))
        value = self._results.pop(0) if self._results else None
        return _FakeResult(value)

    def begin_nested(self):
        class _Nested:
            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, *exc):
                return False

        return _Nested()


@pytest.mark.asyncio
async def test_watermark_is_read_from_the_state_layer_only():
    session = _FakeSession(["mart.inventory_state", datetime(2026, 10, 24, 8, 0)])

    value = await load_collection_watermark(session, "miaoshou")

    assert value == datetime(2026, 10, 24, 8, 0)
    joined = " ".join(sql for sql, _params in session.executed)
    assert "to_regclass('mart.inventory_state')" in joined
    assert "MAX(row_seen_at)" in joined
    for forbidden in ("raw_data->>", "semantic.fact_orders_atomic", "b_class."):
        assert forbidden not in joined


@pytest.mark.asyncio
async def test_watermark_returns_none_when_the_state_layer_is_missing():
    """状态层不存在 → 不发出会失败的查询，直接返回 None（走首采长窗口）。"""
    session = _FakeSession([None])

    value = await load_collection_watermark(session, "miaoshou")

    assert value is None
    # 只探了一次存在性，没有再发实际查询
    assert len(session.executed) == 1
    assert "to_regclass" in session.executed[0][0]


@pytest.mark.asyncio
async def test_last_failed_run_start_is_read_from_collection_config_runs():
    session = _FakeSession([datetime(2026, 10, 24, 3, 0)])

    value = await load_last_failed_run_start(session, 42)

    assert value == datetime(2026, 10, 24, 3, 0)
    joined = " ".join(sql for sql, _params in session.executed)
    assert "core.collection_config_runs" in joined
    for forbidden in ("raw_data->>", "semantic.fact_orders_atomic"):
        assert forbidden not in joined


@pytest.mark.asyncio
async def test_last_failed_run_start_is_none_when_every_run_succeeded():
    session = _FakeSession([None])

    value = await load_last_failed_run_start(session, 42)

    assert value is None
