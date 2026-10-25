from datetime import datetime, timezone

from backend.services.data_pipeline.inventory_state_refresh_service import (
    CHANGE_REASON_FIRST,
    CHANGE_REASON_RESTOCKED,
    CHANGE_REASON_UNCHANGED,
    InventoryStateRefreshService,
    pick_latest_per_key,
    resolve_state_transition,
)

OBSERVED = datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)
INGESTED = datetime(2026, 10, 24, 4, 0, tzinfo=timezone.utc)
CREATED = datetime(2025, 1, 9, 21, 30, tzinfo=timezone.utc)
PREV_ADDED = datetime(2026, 2, 1, tzinfo=timezone.utc)


def _incoming(**overrides):
    row = {
        "platform_code": "miaoshou",
        "sku_key": "SKU-1",
        "warehouse_name": "新加坡",
        "available_stock": 10,
        "on_hand_stock": 10,
        "reserved_stock": 0,
        "observed_at": OBSERVED,
        "created_at": CREATED,
        "ingest_timestamp": INGESTED,
    }
    row.update(overrides)
    return row


def _previous(**overrides):
    row = {
        "available_stock": 10,
        "on_hand_stock": 10,
        "reserved_stock": 0,
        "stock_added_at": PREV_ADDED,
        "created_at": CREATED,
    }
    row.update(overrides)
    return row


def test_first_observation_uses_creation_time_as_baseline():
    """首次观测没有「上次进货」历史 → 用创建时间（首次铺货 ≈ 首次进货）。"""
    result = resolve_state_transition(previous=None, incoming=_incoming())

    assert result["stock_changed"] is True
    assert result["change_reason"] == CHANGE_REASON_FIRST
    assert result["stock_added_at"] == CREATED


def test_restock_advances_added_time_to_row_timestamp():
    """库存总量增加 = 进货 → 计时器重置到本次的行级时间戳。"""
    result = resolve_state_transition(
        previous=_previous(on_hand_stock=10),
        incoming=_incoming(available_stock=30, on_hand_stock=30),
    )

    assert result["stock_changed"] is True
    assert result["change_reason"] == CHANGE_REASON_RESTOCKED
    assert result["stock_added_at"] == OBSERVED


def test_sale_does_not_reset_the_timer():
    """★ 经营模式是「卖完不补货」：销售（库存减少）**不能**重置计时器。"""
    result = resolve_state_transition(
        previous=_previous(available_stock=10, on_hand_stock=10),
        incoming=_incoming(available_stock=3, on_hand_stock=3),
    )

    assert result["stock_changed"] is False
    assert result["change_reason"] == CHANGE_REASON_UNCHANGED
    assert result["stock_added_at"] == PREV_ADDED


def test_unchanged_stock_keeps_previous_added_time():
    result = resolve_state_transition(
        previous=_previous(),
        incoming=_incoming(
            observed_at=datetime(2026, 10, 21, 8, 0, tzinfo=timezone.utc)
        ),
    )

    assert result["stock_changed"] is False
    assert result["stock_added_at"] == PREV_ADDED


def test_reservation_change_is_not_a_restock():
    """订单占用/取消订单只动可用库存、不动总量 → 不能被当成进货。"""
    result = resolve_state_transition(
        previous=_previous(available_stock=10, on_hand_stock=10, reserved_stock=0),
        incoming=_incoming(available_stock=7, on_hand_stock=10, reserved_stock=3),
    )

    assert result["stock_changed"] is False
    assert result["stock_added_at"] == PREV_ADDED


def test_numeric_strings_and_numbers_compare_equal():
    result = resolve_state_transition(
        previous=_previous(available_stock="10", on_hand_stock="10"),
        incoming=_incoming(),
    )

    assert result["stock_changed"] is False


def test_pick_latest_prefers_newest_collection_not_newest_timestamp():
    """妙手时间戳可能被批量污染成比真实值更「新」的时刻 → 必须按采集时间取最新。"""
    rows = [
        _incoming(
            available_stock=99,
            observed_at=datetime(2026, 5, 8, 2, 36, 38, tzinfo=timezone.utc),
            ingest_timestamp=datetime(2026, 10, 21, 16, 15, tzinfo=timezone.utc),
        ),
        _incoming(
            available_stock=10,
            observed_at=datetime(2025, 11, 21, 7, 44, 36, tzinfo=timezone.utc),
            ingest_timestamp=datetime(2026, 10, 24, 4, 39, tzinfo=timezone.utc),
        ),
    ]

    latest = pick_latest_per_key(rows)

    assert len(latest) == 1
    selected = next(iter(latest.values()))
    assert selected["available_stock"] == 10
    assert selected["ingest_timestamp"] == datetime(
        2026, 10, 24, 4, 39, tzinfo=timezone.utc
    )


def test_pick_latest_groups_by_sku_and_warehouse():
    rows = [
        _incoming(sku_key="SKU-1", warehouse_name="新加坡"),
        _incoming(sku_key="SKU-1", warehouse_name="马来仓"),
        _incoming(sku_key="SKU-2", warehouse_name="新加坡"),
    ]

    assert len(pick_latest_per_key(rows)) == 3


def test_state_row_keeps_three_timestamps_separated():
    """stock_added_at / row_seen_at / row_written_at 各司其职，不得互相覆盖。"""
    row = InventoryStateRefreshService.build_state_row(
        _incoming(),
        {"stock_changed": True, "stock_added_at": OBSERVED},
    )

    assert row["stock_added_at"] == OBSERVED
    assert row["row_seen_at"] == INGESTED
    assert row["row_written_at"] == OBSERVED
    assert row["created_at"] == CREATED
    assert row["warehouse_name"] == "新加坡"


def test_refresh_targets_are_dependency_ordered():
    targets = InventoryStateRefreshService(db=None).build_refresh_targets()

    assert targets.index("semantic.fact_inventory_snapshot") < targets.index(
        "mart.inventory_state"
    )
