from backend.services.inventory.inventory_dos_service import (
    DOS_STATUS_COMPUTABLE,
    DOS_STATUS_NO_STOCK,
    DOS_STATUS_STOCKOUT,
    DOS_STATUS_ZERO_SALES,
    classify_dos_status,
    compute_dos,
)


def test_dos_is_available_stock_divided_by_daily_sales():
    """DOS = 可用库存 ÷ (窗口销量 ÷ 窗口天数)，单位：天。"""
    value = compute_dos(available_stock=45, window_sales=30, window_days=30)

    assert value is not None
    assert float(value) == 45.0


def test_dos_uses_ninety_day_window_by_default():
    value = compute_dos(available_stock=90, window_sales=90)

    assert float(value) == 90.0


def test_dos_is_none_when_sales_missing():
    assert compute_dos(available_stock=10, window_sales=None) is None


def test_dos_is_none_when_zero_sales():
    """零销量不是「算得出」——交给状态标签表达。"""
    assert compute_dos(available_stock=10, window_sales=0) is None


def test_dos_is_none_when_no_stock():
    assert compute_dos(available_stock=0, window_sales=5) is None


def test_dos_never_returns_a_sentinel_value():
    """绝不能用 9999 之类的哨兵冒充「算不出」。"""
    for args in (
        {"available_stock": 10, "window_sales": None},
        {"available_stock": 10, "window_sales": 0},
        {"available_stock": 0, "window_sales": 5},
    ):
        value = compute_dos(**args)
        assert value is None or value < 9999


def test_dos_status_distinguishes_four_states():
    assert (
        classify_dos_status(available_stock=10, window_sales=5) == DOS_STATUS_COMPUTABLE
    )
    assert (
        classify_dos_status(available_stock=10, window_sales=0) == DOS_STATUS_ZERO_SALES
    )
    assert classify_dos_status(available_stock=0, window_sales=5) == DOS_STATUS_STOCKOUT
    assert (
        classify_dos_status(available_stock=0, window_sales=0) == DOS_STATUS_ZERO_SALES
    )
    assert (
        classify_dos_status(available_stock=None, window_sales=None)
        == DOS_STATUS_NO_STOCK
    )


def test_dos_accepts_numeric_strings():
    value = compute_dos(available_stock="45", window_sales="30", window_days=30)

    assert value is not None
    assert float(value) == 45.0
