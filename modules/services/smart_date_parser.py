#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart date parser used by ingestion pipeline.

Capabilities:
- Try multiple parsing strategies (dayfirst True/False)
- Handle Excel serial numbers
- Normalize to date (drop time), with optional granularity semantics
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, Optional

import pandas as pd


def _from_excel_serial(value: float) -> Optional[date]:
    try:
        # Excel serial date: 1899-12-30 is day 0 for pandas
        # pandas.to_datetime will handle most cases directly
        dt = pd.to_datetime(float(value), unit="D", origin="1899-12-30")
        return dt.date()
    except Exception:
        return None


def detect_dayfirst(samples: Iterable[str]) -> Optional[bool]:
    """Heuristically decide whether dayfirst should be used.

    Returns True/False or None if undecidable.
    """
    true_hits = false_hits = 0
    for s in samples:
        if not s:
            continue
        t = str(s).strip()
        if not t or t.lower() == "nan":
            continue
        try:
            # try dd/mm/yyyy vs mm/dd/yyyy disambiguation by values > 12
            parts = [p for p in t.replace("-", "/").split("/") if p]
            if len(parts) >= 3:
                a = int(parts[0]); b = int(parts[1])
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


def parse_date(value, *, prefer_dayfirst: Optional[bool] = None, granularity: str = "daily") -> Optional[date]:
    """Parse a variety of date representations into a date object.

    - prefer_dayfirst: if specified, pass to pandas.to_datetime
    - granularity: 'daily'|'weekly'|'monthly' -> used only by callers to set metric_date semantics
    """
    if value is None:
        return None
    # direct date/datetime
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    # excel serial
    try:
        if isinstance(value, (int, float)):
            d = _from_excel_serial(value)
            if d:
                return d
    except Exception:
        pass
    s = str(value).strip()
    if not s:
        return None

    # try pandas with configured dayfirst
    for dayfirst in ([prefer_dayfirst] if prefer_dayfirst is not None else [None, True, False]):
        try:
            dt = pd.to_datetime(s, dayfirst=bool(dayfirst), errors="raise")
            return dt.date()
        except Exception:
            continue

    # final resort: parse common formats
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    return None


