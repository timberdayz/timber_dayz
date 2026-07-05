from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Dict
from zoneinfo import ZoneInfo


DEFAULT_AVAILABLE_AFTER_TIME = "06:00"
DEFAULT_TIMEZONE = ZoneInfo("Asia/Hong_Kong")

DYNAMIC_STRATEGY_TO_GRANULARITY = {
    "previous_day": "daily",
    "current_week_to_available_day": "weekly",
    "current_month_to_available_day": "monthly",
}

DEFAULT_DYNAMIC_TIME_SELECTION_BY_GRANULARITY = {
    "daily": "previous_day",
    "weekly": "current_week_to_available_day",
    "monthly": "current_month_to_available_day",
}

DYNAMIC_TIME_SELECTION_LABELS = {
    "previous_day": "昨天",
    "current_week_to_available_day": "本周累计到最近可采集日",
    "current_month_to_available_day": "本月累计到最近可采集日",
}


def build_dynamic_time_selection(granularity: str) -> Dict[str, str]:
    normalized = str(granularity or "").strip().lower()
    strategy = DEFAULT_DYNAMIC_TIME_SELECTION_BY_GRANULARITY.get(normalized)
    if not strategy:
        raise ValueError(f"unsupported granularity for dynamic time selection: {granularity}")
    return {
        "mode": "dynamic",
        "strategy": strategy,
        "available_after_time": DEFAULT_AVAILABLE_AFTER_TIME,
    }


def is_dynamic_time_selection(time_selection: Dict[str, Any] | None) -> bool:
    return str((time_selection or {}).get("mode") or "").strip().lower() == "dynamic"


def resolve_collection_time_window(
    time_selection: Dict[str, Any],
    *,
    now: datetime | None = None,
) -> Dict[str, Any]:
    strategy = str((time_selection or {}).get("strategy") or "").strip().lower()
    if strategy not in DYNAMIC_STRATEGY_TO_GRANULARITY:
        raise ValueError(f"unsupported dynamic time selection strategy: {strategy or 'empty'}")

    available_after_time = str(
        (time_selection or {}).get("available_after_time")
        or DEFAULT_AVAILABLE_AFTER_TIME
    ).strip()
    current = _normalize_now(now)
    available_day = _resolve_available_day(current, available_after_time)

    if strategy == "previous_day":
        start = end = available_day
    elif strategy == "current_week_to_available_day":
        start = available_day - timedelta(days=available_day.weekday())
        end = available_day
    elif strategy == "current_month_to_available_day":
        start = available_day.replace(day=1)
        end = available_day
    else:
        raise ValueError(f"unsupported dynamic time selection strategy: {strategy}")

    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "time_selection": normalize_dynamic_time_selection(time_selection),
        "time_window_label": DYNAMIC_TIME_SELECTION_LABELS[strategy],
        "available_after_time": available_after_time,
        "available_data_date": available_day.isoformat(),
    }


def normalize_dynamic_time_selection(time_selection: Dict[str, Any]) -> Dict[str, str]:
    strategy = str((time_selection or {}).get("strategy") or "").strip().lower()
    if strategy not in DYNAMIC_STRATEGY_TO_GRANULARITY:
        raise ValueError(f"unsupported dynamic time selection strategy: {strategy or 'empty'}")
    return {
        "mode": "dynamic",
        "strategy": strategy,
        "available_after_time": str(
            (time_selection or {}).get("available_after_time")
            or DEFAULT_AVAILABLE_AFTER_TIME
        ).strip(),
    }


def derive_granularity_from_dynamic_time_selection(time_selection: Dict[str, Any]) -> str:
    normalized = normalize_dynamic_time_selection(time_selection)
    return DYNAMIC_STRATEGY_TO_GRANULARITY[normalized["strategy"]]


def _normalize_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(DEFAULT_TIMEZONE)
    if now.tzinfo is None:
        return now.replace(tzinfo=DEFAULT_TIMEZONE)
    return now.astimezone(DEFAULT_TIMEZONE)


def _resolve_available_day(current: datetime, available_after_time: str) -> date:
    cutoff = _parse_available_after_time(available_after_time)
    days_back = 1 if current.time() >= cutoff else 2
    return current.date() - timedelta(days=days_back)


def _parse_available_after_time(value: str) -> time:
    parts = str(value or DEFAULT_AVAILABLE_AFTER_TIME).split(":")
    if len(parts) < 2:
        raise ValueError(f"invalid available_after_time: {value}")
    return time(hour=int(parts[0]), minute=int(parts[1]))
