from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, TypeVar


T = TypeVar("T")


def select_effective_shop_breakdowns(
    breakdowns: Iterable[T],
    period_start: date,
    period_end: date,
) -> list[T]:
    rows = list(breakdowns)
    scoped_rows = [
        row
        for row in rows
        if _is_period_scoped(row, period_start=period_start, period_end=period_end)
    ]
    if scoped_rows:
        return scoped_rows

    return [row for row in rows if _is_legacy_unscoped(row)]


def _is_period_scoped(row: object, *, period_start: date, period_end: date) -> bool:
    row_start = _to_date(getattr(row, "period_start", None))
    row_end = _to_date(getattr(row, "period_end", None))
    if row_start is None or row_end is None:
        return False
    return row_start <= period_end and row_end >= period_start


def _is_legacy_unscoped(row: object) -> bool:
    return getattr(row, "period_start", None) is None and getattr(row, "period_end", None) is None


def _to_date(value):
    if isinstance(value, datetime):
        return value.date()
    return value
