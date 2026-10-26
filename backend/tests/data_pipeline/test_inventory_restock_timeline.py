"""「上次进货时间」唯一实现的单测。

这个模块是**库龄层**与**状态层**共同的口径来源，
它一旦算错，档位 / 折扣 / 最低售价 / 积压会一起错。
"""

from __future__ import annotations

from datetime import date

from backend.services.data_pipeline.inventory_restock_timeline import (
    REASON_FIRST_SEEN,
    REASON_RESTOCKED,
    aggregate_sku_timeline,
    replay_restock_timeline,
)


def _row(
    *,
    warehouse: str = "新加坡",
    snapshot_date: date,
    on_hand: int,
    sku: str = "SKU-1",
    platform: str = "miaoshou",
    ingest: str = "",
) -> dict:
    return {
        "platform_code": platform,
        "sku_key": sku,
        "warehouse_name": warehouse,
        "snapshot_date": snapshot_date,
        "on_hand_stock": on_hand,
        "last_ingest_timestamp": ingest,
    }


def test_first_frame_anchors_at_that_frame():
    """第一次见到这一行 → 从这一帧起算（0 天）。"""
    result = replay_restock_timeline([_row(snapshot_date=date(2026, 9, 1), on_hand=5)])

    timeline = result[("miaoshou", "SKU-1", "新加坡")]
    assert timeline.anchor_date == date(2026, 9, 1)
    assert timeline.anchor_reason == REASON_FIRST_SEEN
    assert timeline.previous_qty is None
    assert timeline.current_qty == 5


def test_stock_increase_resets_anchor_to_that_frame():
    """库存总量增加 = 进货 → 计时器清零，锚点落在增加那一帧。"""
    result = replay_restock_timeline(
        [
            _row(snapshot_date=date(2026, 9, 1), on_hand=5),
            _row(snapshot_date=date(2026, 9, 14), on_hand=8),
        ]
    )

    timeline = result[("miaoshou", "SKU-1", "新加坡")]
    assert timeline.anchor_date == date(2026, 9, 14)
    assert timeline.anchor_reason == REASON_RESTOCKED


def test_sales_do_not_reset_anchor():
    """卖货（减少）不重置计时器 —— 补货才是新的开始。"""
    result = replay_restock_timeline(
        [
            _row(snapshot_date=date(2026, 9, 1), on_hand=5),
            _row(snapshot_date=date(2026, 9, 14), on_hand=2),
            _row(snapshot_date=date(2026, 10, 1), on_hand=0),
        ]
    )

    timeline = result[("miaoshou", "SKU-1", "新加坡")]
    assert timeline.anchor_date == date(2026, 9, 1)
    assert timeline.anchor_reason == REASON_FIRST_SEEN


def test_uses_total_stock_not_available_stock():
    """取消订单只动可用库存、不动总量 → **不能**被当成进货。

    这里只有 ``available_stock`` 在涨（模拟取消订单），``on_hand_stock`` 不变。
    """
    rows = [
        {
            "platform_code": "miaoshou",
            "sku_key": "SKU-1",
            "warehouse_name": "新加坡",
            "snapshot_date": date(2026, 9, 1),
            "on_hand_stock": 5,
            "available_stock": 1,
        },
        {
            "platform_code": "miaoshou",
            "sku_key": "SKU-1",
            "warehouse_name": "新加坡",
            "snapshot_date": date(2026, 9, 14),
            "on_hand_stock": 5,
            "available_stock": 4,
        },
    ]
    result = replay_restock_timeline(rows)

    timeline = result[("miaoshou", "SKU-1", "新加坡")]
    assert timeline.anchor_date == date(2026, 9, 1), "取消订单不能被当成进货"


def test_aggregate_sku_takes_earliest_anchor_across_warehouses():
    """SKU 级 = 各仓取最长 → 取**最早**的锚点（一个仓压着，整体就压着）。"""
    rows = [
        _row(warehouse="A", snapshot_date=date(2026, 9, 1), on_hand=5),
        _row(warehouse="A", snapshot_date=date(2026, 10, 1), on_hand=2),
        _row(warehouse="B", snapshot_date=date(2026, 9, 1), on_hand=3),
        _row(warehouse="B", snapshot_date=date(2026, 10, 1), on_hand=9),
    ]
    timelines = replay_restock_timeline(rows)

    aggregated = aggregate_sku_timeline(timelines)
    sku = aggregated[("miaoshou", "SKU-1")]

    # A 仓最后一次进货在 09-01（之后只卖不补），B 仓在 10-01 进货
    assert sku.anchor_date == date(2026, 9, 1)
    assert sku.current_qty == 11
    assert sku.warehouse_count == 2


def test_aggregate_sku_ignores_empty_warehouses_for_count():
    """已清空的仓不压资金 → 不计入仓数。"""
    rows = [
        _row(warehouse="A", snapshot_date=date(2026, 9, 1), on_hand=5),
        _row(warehouse="A", snapshot_date=date(2026, 10, 1), on_hand=0),
        _row(warehouse="B", snapshot_date=date(2026, 9, 1), on_hand=3),
    ]
    timelines = replay_restock_timeline(rows)

    aggregated = aggregate_sku_timeline(timelines)
    sku = aggregated[("miaoshou", "SKU-1")]

    assert sku.warehouse_count == 1
    assert sku.current_qty == 3


def test_frames_are_ordered_by_snapshot_date_then_ingest():
    """帧序 = (快照日期, 采集时刻) —— 不能按传入顺序。"""
    rows = [
        _row(snapshot_date=date(2026, 10, 1), on_hand=2, ingest="2026-10-01T00:00:00"),
        _row(snapshot_date=date(2026, 9, 1), on_hand=5, ingest="2026-09-01T00:00:00"),
    ]
    result = replay_restock_timeline(rows)

    timeline = result[("miaoshou", "SKU-1", "新加坡")]
    assert timeline.anchor_date == date(2026, 9, 1)
    assert timeline.current_qty == 2
