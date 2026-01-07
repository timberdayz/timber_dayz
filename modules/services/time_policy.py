from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional, Tuple, Literal

from modules.components.date_picker.base import DateOption

Mode = Literal["quick", "custom", "week_index"]


@dataclass
class RollingDaysPolicy:
    days: int  # 7 or 28 (for TikTok)


@dataclass
class CustomRangePolicy:
    start: date
    end: date


@dataclass
class WeekInMonthPolicy:
    year: int
    month: int
    week_idx: int  # 1-based


def resolve_for_tiktok(policy) -> Tuple[Mode, dict]:
    """Map a generic policy to a TikTok-specific selection plan.

    Returns (mode, payload)
    - quick: { option: DateOption }
    - custom: { start: date, end: date }
    - week_index: { year:int, month:int, week_idx:int }
    """
    if isinstance(policy, RollingDaysPolicy):
        if policy.days == 7:
            return "quick", {"option": DateOption.LAST_7_DAYS}
        if policy.days == 28:
            return "quick", {"option": DateOption.LAST_28_DAYS}
        raise ValueError("TikTok only supports rolling days of 7 or 28 for quick selection")
    if isinstance(policy, CustomRangePolicy):
        return "custom", {"start": policy.start, "end": policy.end}
    if isinstance(policy, WeekInMonthPolicy):
        return "week_index", {"year": policy.year, "month": policy.month, "week_idx": policy.week_idx}
    raise TypeError("Unsupported time policy type")


def apply_time_policy_tiktok(page, adapter, policy) -> Tuple[bool, str]:
    """Apply the time policy using TikTok DatePicker component.

    This function does not navigate; it assumes the page is already at the target
    analytics section with the date picker visible via trigger button.
    """
    mode, payload = resolve_for_tiktok(policy)
    dp = adapter.date_picker()

    try:
        attempts = 3
        backoffs = [600, 1000, 1600]
        last_msg = "failed"
        for i in range(attempts):
            if mode == "quick":
                res = dp.run(page, payload["option"])  # DatePickResult
                ok = bool(getattr(res, "success", False))
                msg = getattr(res, "message", None) or ("quick-ok" if ok else "quick-failed")
                if ok:
                    return True, msg
                last_msg = msg
            elif mode == "week_index":
                ok = bool(dp.select_week_index(page, payload["year"], payload["month"], payload["week_idx"]))
                if ok:
                    return True, "week-index-ok"
                last_msg = "week-index-failed"
            elif mode == "custom":
                ok = bool(dp.select_custom_range(page, payload["start"], payload["end"]))
                if ok:
                    return True, "custom-ok"
                last_msg = "custom-failed"
            else:
                return False, "unknown mode"

            # Retry path for slow renders / iframe refresh
            if i < attempts - 1:
                try:
                    # Try reopening/ensuring panel; safe if already open
                    if hasattr(dp, "_open_panel"):
                        dp._open_panel(page)
                except Exception:
                    pass
                try:
                    page.wait_for_timeout(backoffs[min(i, len(backoffs) - 1)])
                except Exception:
                    pass
        return False, last_msg
    except Exception as e:
        return False, str(e)

    return False, "unknown mode"

