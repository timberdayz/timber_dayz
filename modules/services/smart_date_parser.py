#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart date parser used by the ingestion pipeline.

This module now prefers explicit year-position parsing before any
dayfirst-style heuristics, and it exposes a strict declared-format
parser for template-governed ingestion.
"""

from __future__ import annotations

from datetime import date, datetime
import re
from typing import Iterable, Optional

import pandas as pd


_YEAR_FIRST_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d")
_YEAR_FIRST_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
)
_DAY_FIRST_DATE_FORMATS = ("%d-%m-%Y", "%d/%m/%Y")
_DAY_FIRST_DATETIME_FORMATS = (
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
)
_DECLARED_SINGLE_FORMATS = {
    "yyyy-mm-dd": ("%Y-%m-%d", False),
    "yyyy/mm/dd": ("%Y/%m/%d", False),
    "yyyy-mm-dd hh:mm": ("%Y-%m-%d %H:%M", True),
    "yyyy-mm-dd hh:mm:ss": ("%Y-%m-%d %H:%M:%S", True),
    "yyyy/mm/dd hh:mm": ("%Y/%m/%d %H:%M", True),
    "yyyy/mm/dd hh:mm:ss": ("%Y/%m/%d %H:%M:%S", True),
    "dd-mm-yyyy": ("%d-%m-%Y", False),
    "dd/mm/yyyy": ("%d/%m/%Y", False),
    "dd-mm-yyyy hh:mm": ("%d-%m-%Y %H:%M", True),
    "dd-mm-yyyy hh:mm:ss": ("%d-%m-%Y %H:%M:%S", True),
    "dd/mm/yyyy hh:mm": ("%d/%m/%Y %H:%M", True),
    "dd/mm/yyyy hh:mm:ss": ("%d/%m/%Y %H:%M:%S", True),
}
_DECLARED_TIME_FORMATS = {
    "hh:mm": "%H:%M",
    "hh:mm:ss": "%H:%M:%S",
}
_DECLARED_RANGE_BASE_FORMATS = {
    "dd-mm-yyyy-dd-mm-yyyy": "%d-%m-%Y",
    "dd/mm/yyyy-dd/mm/yyyy": "%d/%m/%Y",
    "yyyy-mm-dd-yyyy-mm-dd": "%Y-%m-%d",
    "yyyy/mm/dd-yyyy/mm/dd": "%Y/%m/%d",
}


def _from_excel_serial(value: float) -> Optional[date]:
    try:
        dt = pd.to_datetime(float(value), unit="D", origin="1899-12-30")
        return dt.date()
    except Exception:
        return None


def detect_dayfirst(samples: Iterable[str]) -> Optional[bool]:
    """Heuristically decide whether dayfirst should be used."""
    true_hits = false_hits = 0
    for s in samples:
        if not s:
            continue
        t = str(s).strip()
        if not t or t.lower() == "nan":
            continue
        try:
            parts = [p for p in t.replace("-", "/").split("/") if p]
            if len(parts) >= 3:
                a = int(parts[0])
                b = int(parts[1])
                if a > 12 and b <= 12:
                    true_hits += 1
                if b > 12 and a <= 12:
                    false_hits += 1
        except Exception:
            continue
    if true_hits > false_hits and true_hits >= 1:
        return True
    if false_hits > true_hits and false_hits >= 1:
        return False
    return None


def _normalize_string(value: object) -> str:
    return str(value).strip()


def _try_datetime_formats(value: str, formats: tuple[str, ...]) -> Optional[datetime]:
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _try_date_formats(value: str, formats: tuple[str, ...]) -> Optional[date]:
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_explicit_year_position_date(value: str) -> Optional[date]:
    if re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?$", value):
        dt = _try_datetime_formats(value, _YEAR_FIRST_DATETIME_FORMATS)
        if dt:
            return dt.date()
        return _try_date_formats(value, _YEAR_FIRST_DATE_FORMATS)

    if re.match(r"^\d{1,2}[-/]\d{1,2}[-/]\d{4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?$", value):
        dt = _try_datetime_formats(value, _DAY_FIRST_DATETIME_FORMATS)
        if dt:
            return dt.date()
        return _try_date_formats(value, _DAY_FIRST_DATE_FORMATS)

    return None


def _split_declared_range_value(value: str, component_length: int) -> tuple[str, str]:
    normalized = value.strip()
    for separator in (" - ", "~", " to "):
        if separator in normalized:
            start_str, end_str = normalized.split(separator, 1)
            return start_str.strip(), end_str.strip()

    if len(normalized) >= component_length * 2 + 1:
        return normalized[:component_length].strip(), normalized[-component_length:].strip()

    raise ValueError(f"unable to split declared date range: {value}")


def _coerce_anchor_date(date_anchor: object) -> date:
    if isinstance(date_anchor, datetime):
        return date_anchor.date()
    if isinstance(date_anchor, date):
        return date_anchor
    parsed_anchor = parse_date(date_anchor)
    if parsed_anchor:
        return parsed_anchor
    raise ValueError("date_anchor is required for time-only parsing")


def parse_date_by_declared_format(
    value: object,
    *,
    date_format: str,
    value_kind: str = "single_date",
    range_pick: Optional[str] = None,
    date_anchor: object = None,
) -> tuple[Optional[date], Optional[datetime]]:
    """Parse a value strictly by its declared template format."""
    if value is None:
        return (None, None)
    if isinstance(value, date) and not isinstance(value, datetime):
        return (value, None)
    if isinstance(value, datetime):
        return (value.date(), value)

    raw = _normalize_string(value)
    if not raw:
        return (None, None)

    normalized_format = str(date_format).strip().lower()
    normalized_kind = str(value_kind).strip().lower()
    if normalized_kind not in {
        "single_date",
        "single_datetime",
        "time_of_day",
        "date_range",
        "datetime_range",
        "time_range",
    }:
        raise ValueError(f"unsupported value_kind: {value_kind}")

    if normalized_kind in {"single_date", "single_datetime"}:
        format_spec = _DECLARED_SINGLE_FORMATS.get(normalized_format)
        if not format_spec:
            raise ValueError(f"unsupported declared date format: {date_format}")
        fmt, has_time = format_spec
        parsed = datetime.strptime(raw, fmt)
        return (parsed.date(), parsed if has_time else None)

    if normalized_kind == "time_of_day":
        fmt = _DECLARED_TIME_FORMATS.get(normalized_format)
        if not fmt:
            raise ValueError(f"unsupported declared time format: {date_format}")
        anchor = _coerce_anchor_date(date_anchor)
        parsed_time = datetime.strptime(raw, fmt).time()
        parsed = datetime.combine(anchor, parsed_time)
        return (parsed.date(), parsed)

    if normalized_kind == "datetime_range":
        format_spec = _DECLARED_SINGLE_FORMATS.get(normalized_format)
        if not format_spec or not format_spec[1]:
            raise ValueError(f"unsupported declared datetime range format: {date_format}")
        if range_pick not in {"start", "end"}:
            raise ValueError(f"range_pick is required for declared datetime range format: {date_format}")
        fmt = format_spec[0]
        component_length = len(datetime(2026, 4, 18, 13, 0, 0).strftime(fmt))
        start_str, end_str = _split_declared_range_value(raw, component_length)
        picked = start_str if range_pick == "start" else end_str
        parsed = datetime.strptime(picked, fmt)
        return (parsed.date(), parsed)

    if normalized_kind == "time_range":
        fmt = _DECLARED_TIME_FORMATS.get(normalized_format)
        if not fmt:
            raise ValueError(f"unsupported declared time range format: {date_format}")
        if range_pick not in {"start", "end"}:
            raise ValueError(f"range_pick is required for declared time range format: {date_format}")
        anchor = _coerce_anchor_date(date_anchor)
        component_length = len(datetime(2026, 4, 18, 13, 0, 0).strftime(fmt))
        start_str, end_str = _split_declared_range_value(raw, component_length)
        picked = start_str if range_pick == "start" else end_str
        parsed_time = datetime.strptime(picked, fmt).time()
        parsed = datetime.combine(anchor, parsed_time)
        return (parsed.date(), parsed)

    base_fmt = _DECLARED_RANGE_BASE_FORMATS.get(normalized_format)
    if not base_fmt:
        raise ValueError(f"unsupported declared range format: {date_format}")
    if range_pick not in {"start", "end"}:
        raise ValueError(f"range_pick is required for declared date range format: {date_format}")

    component_length = len(datetime(2026, 4, 18).strftime(base_fmt))
    start_str, end_str = _split_declared_range_value(raw, component_length)
    start_date = datetime.strptime(start_str, base_fmt).date()
    end_date = datetime.strptime(end_str, base_fmt).date()
    return ((start_date, None) if range_pick == "start" else (end_date, None))


def parse_date(value, *, prefer_dayfirst: Optional[bool] = None, granularity: str = "daily") -> Optional[date]:
    """Parse a variety of date representations into a date object."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()

    try:
        if isinstance(value, (int, float)):
            parsed_excel = _from_excel_serial(value)
            if parsed_excel:
                return parsed_excel
    except Exception:
        pass

    s = _normalize_string(value)
    if not s:
        return None

    explicit = _parse_explicit_year_position_date(s)
    if explicit:
        return explicit

    for dayfirst in ([prefer_dayfirst] if prefer_dayfirst is not None else [None, True, False]):
        try:
            dt = pd.to_datetime(s, dayfirst=bool(dayfirst), errors="raise")
            return dt.date()
        except Exception:
            continue

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None
