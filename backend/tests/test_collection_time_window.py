from datetime import datetime
from zoneinfo import ZoneInfo

from backend.schemas.collection import TimeSelectionPayload
from backend.services.collection_time_window import (
    build_dynamic_time_selection,
    resolve_collection_time_window,
)


HK = ZoneInfo("Asia/Hong_Kong")


def test_month_window_before_cutoff_uses_day_before_yesterday():
    window = resolve_collection_time_window(
        {"mode": "dynamic", "strategy": "current_month_to_available_day"},
        now=datetime(2026, 7, 5, 5, 59, tzinfo=HK),
    )

    assert window["start_date"] == "2026-07-01"
    assert window["end_date"] == "2026-07-03"
    assert window["date_from"] == "2026-07-01"
    assert window["date_to"] == "2026-07-03"


def test_month_window_at_cutoff_uses_yesterday():
    window = resolve_collection_time_window(
        {"mode": "dynamic", "strategy": "current_month_to_available_day"},
        now=datetime(2026, 7, 5, 6, 0, tzinfo=HK),
    )

    assert window["start_date"] == "2026-07-01"
    assert window["end_date"] == "2026-07-04"


def test_previous_day_window_respects_cutoff():
    before_cutoff = resolve_collection_time_window(
        {"mode": "dynamic", "strategy": "previous_day"},
        now=datetime(2026, 7, 5, 5, 59, tzinfo=HK),
    )
    after_cutoff = resolve_collection_time_window(
        {"mode": "dynamic", "strategy": "previous_day"},
        now=datetime(2026, 7, 5, 6, 0, tzinfo=HK),
    )

    assert before_cutoff["start_date"] == "2026-07-03"
    assert before_cutoff["end_date"] == "2026-07-03"
    assert after_cutoff["start_date"] == "2026-07-04"
    assert after_cutoff["end_date"] == "2026-07-04"


def test_week_window_starts_on_current_week_monday():
    window = resolve_collection_time_window(
        {"mode": "dynamic", "strategy": "current_week_to_available_day"},
        now=datetime(2026, 7, 8, 7, 0, tzinfo=HK),
    )

    assert window["start_date"] == "2026-07-06"
    assert window["end_date"] == "2026-07-07"


def test_dynamic_time_selection_payload_is_accepted():
    payload = TimeSelectionPayload(
        mode="dynamic",
        strategy="current_month_to_available_day",
    )

    assert payload.mode == "dynamic"
    assert payload.strategy == "current_month_to_available_day"
    assert payload.available_after_time == "06:00"


def test_build_dynamic_time_selection_maps_granularity_defaults():
    assert build_dynamic_time_selection("daily") == {
        "mode": "dynamic",
        "strategy": "previous_day",
        "available_after_time": "06:00",
    }
    assert build_dynamic_time_selection("weekly")["strategy"] == "current_week_to_available_day"
    assert build_dynamic_time_selection("monthly")["strategy"] == "current_month_to_available_day"
