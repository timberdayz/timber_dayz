from datetime import date, datetime, timezone

from backend.services.inventory.inventory_restock_service import (
    RESTOCK_TIER_ACTIVE,
    RESTOCK_TIER_DEEP,
    RESTOCK_TIER_LIGHT,
    RESTOCK_TIER_MID,
    RESTOCK_TIER_UNKNOWN,
    aggregate_sku_restock_days,
    aggregate_sku_restock_tier,
    build_restock_row,
    classify_restock_tier,
    compute_days_since_restock,
    has_stock,
)

AS_OF = date(2026, 10, 24)


def test_days_since_restock_counts_from_last_restock():
    assert (
        compute_days_since_restock(
            stock_added_at=datetime(2026, 7, 26, 3, 0, tzinfo=timezone.utc),
            as_of=AS_OF,
        )
        == 90
    )


def test_days_since_restock_accepts_plain_dates():
    assert (
        compute_days_since_restock(stock_added_at=date(2026, 4, 24), as_of=AS_OF) == 183
    )


def test_days_since_restock_is_zero_when_restocked_today():
    assert compute_days_since_restock(stock_added_at=AS_OF, as_of=AS_OF) == 0


def test_days_since_restock_never_goes_negative():
    assert (
        compute_days_since_restock(stock_added_at=date(2026, 11, 1), as_of=AS_OF) == 0
    )


def test_days_since_restock_is_unknown_without_baseline():
    assert compute_days_since_restock(stock_added_at=None, as_of=AS_OF) is None
    assert compute_days_since_restock(stock_added_at=AS_OF, as_of=None) is None


def test_tier_thresholds_follow_pricing_policy_table():
    """门槛与商品中心档位表一致：0 / 60 / 90 / 120。"""
    assert classify_restock_tier(0) == RESTOCK_TIER_ACTIVE
    assert classify_restock_tier(59) == RESTOCK_TIER_ACTIVE
    assert classify_restock_tier(60) == RESTOCK_TIER_LIGHT
    assert classify_restock_tier(89) == RESTOCK_TIER_LIGHT
    assert classify_restock_tier(90) == RESTOCK_TIER_MID
    assert classify_restock_tier(119) == RESTOCK_TIER_MID
    assert classify_restock_tier(120) == RESTOCK_TIER_DEEP
    assert classify_restock_tier(900) == RESTOCK_TIER_DEEP


def test_unknown_tier_never_falls_back_to_active():
    """缺料不得回落「活跃」——那会让最该降价的 SKU 拿最低折扣。"""
    assert classify_restock_tier(None) == RESTOCK_TIER_UNKNOWN
    assert classify_restock_tier(None) != RESTOCK_TIER_ACTIVE


def test_sku_aggregation_takes_longest_among_warehouses_with_stock():
    rows = [
        {"days_since_restock": 10, "available_stock": 5},
        {"days_since_restock": 240, "available_stock": 3},
        {"days_since_restock": 90, "available_stock": 0},
    ]

    assert aggregate_sku_restock_days(rows) == 240
    assert aggregate_sku_restock_tier(rows) == RESTOCK_TIER_DEEP


def test_sku_aggregation_ignores_warehouses_without_stock():
    rows = [
        {"days_since_restock": 500, "available_stock": 0},
        {"days_since_restock": 45, "available_stock": 2},
    ]

    assert aggregate_sku_restock_days(rows) == 45


def test_sku_aggregation_is_unknown_when_nothing_has_stock():
    rows = [{"days_since_restock": 500, "available_stock": 0}]

    assert aggregate_sku_restock_days(rows) is None
    assert aggregate_sku_restock_tier(rows) == RESTOCK_TIER_UNKNOWN


def test_has_stock_handles_none_and_bad_values():
    assert has_stock({"available_stock": 3}) is True
    assert has_stock({"available_stock": 0}) is False
    assert has_stock({"available_stock": None}) is False
    assert has_stock({"available_stock": "abc"}) is False
    assert has_stock({}) is False


def test_build_restock_row_exposes_tier_and_days():
    row = build_restock_row(
        platform_code="miaoshou",
        sku_key="SKU-1",
        warehouse_name="新加坡",
        stock_added_at=date(2026, 1, 1),
        as_of=AS_OF,
        available_stock=10,
    )

    assert row["days_since_restock"] == 296
    assert row["restock_tier"] == RESTOCK_TIER_DEEP
    assert row["platform_code"] == "miaoshou"
    assert row["warehouse_name"] == "新加坡"
