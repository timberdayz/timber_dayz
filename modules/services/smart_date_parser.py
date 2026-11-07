#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart date parser used by the ingestion pipeline.

This module now prefers explicit year-position parsing before any
dayfirst-style heuristics, and it exposes a strict declared-format
parser for template-governed ingestion.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Iterable, Optional

import pandas as pd

from modules.core.logger import get_logger

logger = get_logger(__name__)


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
    "mm-dd-yyyy": ("%m-%d-%Y", False),
    "mm/dd/yyyy": ("%m/%d/%Y", False),
    "mm-dd-yyyy hh:mm": ("%m-%d-%Y %H:%M", True),
    "mm-dd-yyyy hh:mm:ss": ("%m-%d-%Y %H:%M:%S", True),
    "mm/dd/yyyy hh:mm": ("%m/%d/%Y %H:%M", True),
    "mm/dd/yyyy hh:mm:ss": ("%m/%d/%Y %H:%M:%S", True),
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
_AUTO_COMPANION_FORMAT = "auto_by_companion_period"
_DEFAULT_AUTO_SINGLE_FORMAT_CANDIDATES = tuple(_DECLARED_SINGLE_FORMATS.keys())
_DEFAULT_AUTO_RANGE_FORMAT_CANDIDATES = tuple(_DECLARED_RANGE_BASE_FORMATS.keys())


# ── 宽松解析(探测用)的格式与判定 ──────────────────────────────────
#
# 宽松解析器只服务于**探测/预览**; 入库路径只允许严格声明式
# (:func:`parse_date_by_declared_format`)。
#
# 下面是「年份位置明确」的两种形态:
#   * ``yyyy-mm-dd`` / ``yyyy/mm/dd`` —— 年在前, 唯一, 没有歧义;
#   * ``dd-mm-yyyy`` / ``dd/mm/yyyy`` —— 日与月都 ≤ 12 时**有歧义**,
#     必须靠调用方给列级偏好, 否则落 unknown(不猜)。
_MONTH_FIRST_DATE_FORMATS = ("%m-%d-%Y", "%m/%d/%Y")
_MONTH_FIRST_DATETIME_FORMATS = (
    "%m-%d-%Y %H:%M:%S",
    "%m-%d-%Y %H:%M",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
)

_EXPLICIT_YEAR_FIRST_PATTERN = re.compile(
    r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?$"
)
_EXPLICIT_DAY_MONTH_YEAR_PATTERN = re.compile(
    r"^\d{1,2}[-/]\d{1,2}[-/]\d{4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?$"
)


def _split_day_month_year(value: str) -> Optional[tuple[int, int, int]]:
    """把 ``d/m/Y``(可带时间部分)拆成 ``(first, second, year)``。"""
    head = value.split()[0] if value.split() else value
    parts = re.split(r"[-/]", head)
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None


def _resolve_day_first(
    first: int,
    second: int,
    *,
    prefer_dayfirst: Optional[bool] = None,
) -> Optional[bool]:
    """判定这是 dd/mm 还是 mm/dd。

    Returns:
        True=日-月-年, False=月-日-年, **None=不确定(不猜)**。
    """
    if prefer_dayfirst is not None:
        return bool(prefer_dayfirst)
    if first > 12 and second <= 12:
        return True
    if second > 12 and first <= 12:
        return False
    return None


# ── 对外暴露的「合法声明格式」唯一口径 ───────────────────────────
#
# 为什么要有这一层:
#   模板里写的 date_format 是**运行期**才会被解析器消费的字符串。
#   解析器遇到不认识的 token 会在入库时抛
#   "unsupported declared date format: xxx" —— 整份文件入不了库,
#   而且事前没有任何提示(漂移检测只看列名, 不看值形态)。
#   所以「合法格式」必须有一份**可被保存闸门引用**的白名单,
#   让非法值在**保存时**就被拦住, 而不是等文件进来才炸。
#
# 使用方:
#   - backend/domains/data_platform/routers/field_mapping_templates.py
#     `_validate_field_parse_rules` —— 保存闸门
#   - backend/services/template_save_readiness_service.py
#     样本试解析体检
#   - frontend/src/domains/data_platform/utils/templateFieldParseRules.js
#     DATE_FORMAT_OPTIONS(前端选项表以此为准)
SUPPORTED_DECLARED_DATE_FORMATS: frozenset[str] = frozenset(
    set(_DECLARED_SINGLE_FORMATS.keys())
    | set(_DECLARED_TIME_FORMATS.keys())
    | set(_DECLARED_RANGE_BASE_FORMATS.keys())
    | {_AUTO_COMPANION_FORMAT}
)

# value_kind 决定「这个值长什么样」, date_format 决定「怎么读」——
# 两者必须自洽(例如 date_range 不能配 yyyy-mm-dd 这种单值格式)。
_DECLARED_FORMATS_BY_VALUE_KIND: dict[str, frozenset[str]] = {
    "single_date": frozenset(_DECLARED_SINGLE_FORMATS.keys()),
    "single_datetime": frozenset(_DECLARED_SINGLE_FORMATS.keys()),
    "datetime_range": frozenset(
        token for token, (_fmt, has_time) in _DECLARED_SINGLE_FORMATS.items() if has_time
    ),
    "time_of_day": frozenset(_DECLARED_TIME_FORMATS.keys()),
    "time_range": frozenset(_DECLARED_TIME_FORMATS.keys()),
    "date_range": frozenset(_DECLARED_RANGE_BASE_FORMATS.keys()),
}

# auto_by_companion_period 只对「有候选集」的 value_kind 有效:
# `_candidate_formats_for_auto` 对 time_of_day / time_range 直接抛。
_AUTO_SUPPORTED_VALUE_KINDS: frozenset[str] = frozenset(
    {"single_date", "single_datetime", "datetime_range", "date_range"}
)


def is_supported_declared_date_format(value: object) -> bool:
    """date_format 是否是解析器认识的 token(大小写不敏感)。"""
    return str(value or "").strip().lower() in SUPPORTED_DECLARED_DATE_FORMATS


def declared_date_formats_for_value_kind(value_kind: object) -> frozenset[str]:
    """某个 value_kind 下允许的 date_format 集合(小写 token)。

    未知 value_kind 返回空集合 —— 调用方据此判定「不兼容」而不是「放行」。
    """
    kind = str(value_kind or "").strip().lower()
    formats = set(_DECLARED_FORMATS_BY_VALUE_KIND.get(kind, frozenset()))
    if kind in _AUTO_SUPPORTED_VALUE_KINDS:
        formats.add(_AUTO_COMPANION_FORMAT)
    return frozenset(formats)


def is_declared_date_format_compatible(value_kind: object, date_format: object) -> bool:
    """date_format 与 value_kind 是否自洽。"""
    kind = str(value_kind or "").strip().lower()
    token = str(date_format or "").strip().lower()
    if not kind or not token:
        return False
    return token in declared_date_formats_for_value_kind(kind)


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


def _probe_explicit_year_position(
    value: str,
    *,
    prefer_dayfirst: Optional[bool] = None,
) -> tuple[Optional[date], bool]:
    """探测「年份位置明确」的日期 —— 返回 ``(日期, 是否歧义)``。

    ``d/m/Y`` 这种写法, 当「日」与「月」都 ≤ 12 时, dd/mm 与 mm/dd 会给出
    **不同**的日期(``11/01/2026`` → 1 月 11 日 / 11 月 1 日)。
    这时**不能**默认按日-月-年解 —— 以前就是在这里静默猜错的。

    ``prefer_dayfirst`` 是**调用方已经做完列级判定**的结果:
    给了就尊重它; 没给就必须靠值本身消歧, 消不了就落 unknown(不猜)。
    """
    if _EXPLICIT_YEAR_FIRST_PATTERN.match(value):
        dt = _try_datetime_formats(value, _YEAR_FIRST_DATETIME_FORMATS)
        if dt:
            return dt.date(), False
        parsed = _try_date_formats(value, _YEAR_FIRST_DATE_FORMATS)
        return parsed, False

    if _EXPLICIT_DAY_MONTH_YEAR_PATTERN.match(value):
        parts = _split_day_month_year(value)
        if parts is None:
            return None, False
        first, second, _year = parts
        day_first = _resolve_day_first(first, second, prefer_dayfirst=prefer_dayfirst)
        if day_first is None:
            # 歧义: 日与月都 ≤ 12 ⇒ 不猜, 落 unknown。
            logger.warning(
                "[SmartDateParser] 日期值存在歧义, 落 unknown 不猜: %r "
                "(dd/mm 与 mm/dd 都会解析成功, 需要调用方先判定列级偏好)",
                value,
            )
            return None, True
        formats = _DAY_FIRST_DATE_FORMATS if day_first else _MONTH_FIRST_DATE_FORMATS
        datetime_formats = (
            _DAY_FIRST_DATETIME_FORMATS if day_first else _MONTH_FIRST_DATETIME_FORMATS
        )
        dt = _try_datetime_formats(value, datetime_formats)
        if dt:
            return dt.date(), False
        return _try_date_formats(value, formats), False

    return None, False


def _parse_explicit_year_position_date(
    value: str,
    *,
    prefer_dayfirst: Optional[bool] = None,
) -> Optional[date]:
    """:func:`_probe_explicit_year_position` 的「只要日期」版本。"""
    parsed, _ambiguous = _probe_explicit_year_position(
        value, prefer_dayfirst=prefer_dayfirst
    )
    return parsed


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


def _coerce_optional_date(value: object) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return parse_date(value)


def _is_within_companion_period(
    parsed_date: Optional[date],
    companion_date_from: Optional[date],
    companion_date_to: Optional[date],
) -> bool:
    if parsed_date is None:
        return False
    if companion_date_from and parsed_date < companion_date_from:
        return False
    if companion_date_to and parsed_date > companion_date_to:
        return False
    return True


def _candidate_formats_for_auto(
    *,
    value_kind: str,
    format_candidates: Optional[Iterable[str]],
) -> list[str]:
    candidates = [
        str(candidate).strip().lower()
        for candidate in (format_candidates or [])
        if str(candidate).strip()
    ]
    if candidates:
        return list(dict.fromkeys(candidates))
    if value_kind in {"single_date", "single_datetime", "datetime_range"}:
        return list(_DEFAULT_AUTO_SINGLE_FORMAT_CANDIDATES)
    if value_kind == "date_range":
        return list(_DEFAULT_AUTO_RANGE_FORMAT_CANDIDATES)
    raise ValueError(f"auto companion period does not support value_kind: {value_kind}")


def _parse_by_companion_period(
    value: object,
    *,
    value_kind: str,
    range_pick: Optional[str],
    date_anchor: object,
    companion_date_from: object,
    companion_date_to: object,
    format_candidates: Optional[Iterable[str]],
) -> tuple[Optional[date], Optional[datetime]]:
    start_date = _coerce_optional_date(companion_date_from)
    end_date = _coerce_optional_date(companion_date_to)
    if start_date is None and end_date is None:
        raise ValueError("companion date_from/date_to is required for auto companion period parsing")

    matches: list[tuple[str, Optional[date], Optional[datetime]]] = []
    for candidate in _candidate_formats_for_auto(
        value_kind=value_kind,
        format_candidates=format_candidates,
    ):
        try:
            parsed_date, parsed_datetime = parse_date_by_declared_format(
                value,
                date_format=candidate,
                value_kind=value_kind,
                range_pick=range_pick,
                date_anchor=date_anchor,
            )
        except ValueError:
            continue
        if _is_within_companion_period(parsed_date, start_date, end_date):
            matches.append((candidate, parsed_date, parsed_datetime))

    if not matches:
        raise ValueError("no companion-constrained date format matched")
    if len(matches) > 1:
        candidates = ", ".join(match[0] for match in matches)
        raise ValueError(f"ambiguous companion-constrained date format: {candidates}")
    return matches[0][1], matches[0][2]


def parse_date_by_declared_format(
    value: object,
    *,
    date_format: str,
    value_kind: str = "single_date",
    range_pick: Optional[str] = None,
    date_anchor: object = None,
    companion_date_from: object = None,
    companion_date_to: object = None,
    format_candidates: Optional[Iterable[str]] = None,
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

    if normalized_format == _AUTO_COMPANION_FORMAT:
        return _parse_by_companion_period(
            raw,
            value_kind=normalized_kind,
            range_pick=range_pick,
            date_anchor=date_anchor,
            companion_date_from=companion_date_from,
            companion_date_to=companion_date_to,
            format_candidates=format_candidates,
        )

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


DATE_PROBE_PARSED = "parsed"
"""值被唯一解析出来。"""

DATE_PROBE_AMBIGUOUS = "ambiguous"
"""多个解释都成立(典型: dd/mm 与 mm/dd 都 ≤ 12)⇒ 不猜, 落 unknown。"""

DATE_PROBE_UNPARSED = "unparsed"
"""值压根解不出来。"""


@dataclass(frozen=True)
class DateProbe:
    """一次日期解析探测的结果。

    「不确定」与「解析不出来」是**两回事**:
    * ``ambiguous`` ⇒ 值本身合法, 但有多个解释 ⇒ 需要人来定(列级偏好);
    * ``unparsed`` ⇒ 值不是日期。

    以前这两种情况都被压成 ``None``, 于是调用方分不清
    「需要消歧」与「这个字段根本不是日期」。
    """

    value: Optional[date]
    status: str
    candidates: tuple[date, ...] = ()
    detail: str = ""

    @property
    def parsed(self) -> bool:
        return self.status == DATE_PROBE_PARSED

    @property
    def ambiguous(self) -> bool:
        return self.status == DATE_PROBE_AMBIGUOUS


def probe_date(
    value: object,
    *,
    prefer_dayfirst: Optional[bool] = None,
) -> DateProbe:
    """探测一个值是不是日期、是哪一天 —— **不猜**。

    宽松解析器的**唯一**实现; 其余 6 套日期解析都委派到这里。

    Args:
        value: 待探测的值
        prefer_dayfirst: 调用方已经做完的**列级**判定。
            给了就尊重它(``True``=dd/mm, ``False``=mm/dd);
            没给就必须靠值本身消歧, 消不了 ⇒ ``ambiguous``。

    Returns:
        :class:`DateProbe`; ``value`` 为 ``None`` 表示「落 unknown」。
    """
    if value is None:
        return DateProbe(None, DATE_PROBE_UNPARSED, detail="value is None")
    if isinstance(value, date) and not isinstance(value, datetime):
        return DateProbe(value, DATE_PROBE_PARSED)
    if isinstance(value, datetime):
        return DateProbe(value.date(), DATE_PROBE_PARSED)

    try:
        if isinstance(value, (int, float)):
            parsed_excel = _from_excel_serial(value)
            if parsed_excel:
                return DateProbe(parsed_excel, DATE_PROBE_PARSED)
    except Exception:
        pass

    s = _normalize_string(value)
    if not s:
        return DateProbe(None, DATE_PROBE_UNPARSED, detail="empty value")

    explicit, ambiguous = _probe_explicit_year_position(
        s, prefer_dayfirst=prefer_dayfirst
    )
    if explicit:
        return DateProbe(explicit, DATE_PROBE_PARSED)
    if ambiguous:
        return DateProbe(
            None,
            DATE_PROBE_AMBIGUOUS,
            detail=(
                f"{s!r} 可以按 dd/mm 或 mm/dd 解析成不同日期; "
                "需要调用方提供列级日期偏好(prefer_dayfirst)"
            ),
        )

    for dayfirst in ([prefer_dayfirst] if prefer_dayfirst is not None else [None, True, False]):
        try:
            dt = pd.to_datetime(s, dayfirst=bool(dayfirst), errors="raise")
            return DateProbe(dt.date(), DATE_PROBE_PARSED)
        except Exception:
            continue

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return DateProbe(datetime.strptime(s, fmt).date(), DATE_PROBE_PARSED)
        except ValueError:
            continue
    return DateProbe(None, DATE_PROBE_UNPARSED, detail=f"{s!r} is not a date")


def parse_date(
    value: object,
    *,
    prefer_dayfirst: Optional[bool] = None,
    granularity: str = "daily",
) -> Optional[date]:
    """宽松解析(探测/预览专用) —— **入库路径不允许用它**。

    与旧版的区别: **不再猜**。

    以前 ``11/01/2026`` 会被静默按 dd/mm 解成 1 月 11 日;
    现在「日」与「月」都 ≤ 12 时落 unknown(返回 None)并报警 ——
    要么调用方给出列级偏好(``prefer_dayfirst``),要么人工确认。

    严格声明式解析请用 :func:`parse_date_by_declared_format`。
    """
    probe = probe_date(value, prefer_dayfirst=prefer_dayfirst)
    if probe.ambiguous:
        logger.warning(
            "[SmartDateParser] 日期值歧义, 落 unknown: %s (%s)",
            value,
            probe.detail,
        )
        return None
    return probe.value


def parse_iso_date(value: object) -> Optional[date]:
    """只接受 ISO 形态(``yyyy-mm-dd`` / ``yyyy-mm-ddTHH:MM:SS``)的日期。

    用于「已经是标准格式」的场合(例如数据库里的 date 列)——
    这种场合**没有**日/月歧义, 所以不需要也不应该走宽松解析。
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        return date.fromisoformat(text_value[:10])
    except ValueError:
        return None


def parse_date_strict(
    value: object,
    *,
    prefer_dayfirst: Optional[bool] = None,
) -> Optional[date]:
    """:func:`parse_date` 的「唯一口径」别名 —— 给其它模块委派用。

    语义完全一致: 不猜。歧义 ⇒ None。
    """
    return parse_date(value, prefer_dayfirst=prefer_dayfirst)


# ── 区间切分(唯一实现) ────────────────────────────────────────────
#
# 「2025-08-25 17:01~2025-08-26 11:02」这类值要先切成两半,
# 再分别解析。切分本身**没有**日/月歧义(它只找分隔符),
# 所以这里只负责切, 不负责「这一半是哪一天」。
#
# 以前这段正则在 ``backend/services/field_mapping/type_detector.py`` 里,
# 现在收到这里 —— 区间切分与日期解析必须是一套口径。
_RANGE_SEPARATORS = (
    r"~",
    r"—",
    r"至",
    r"to",
    r"To",
    r"TO",
    r"到",
    r"-",
)

_RANGE_DATE_TIME_PATTERN = (
    r"\d{4}[-/]\d{1,2}[-/]\d{1,2}"
    r"(?:[-]\d{1,2}:\d{2}(?::\d{2})?|\s+\d{1,2}:\d{2}(?::\d{2})?)?"
)
_RANGE_DATE_PATTERN = r"(?:\d{1,2}[-/]\d{1,2}[-/]\d{4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})"

_RANGE_DASH_TIME_CLEANUP = re.compile(
    r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})-(\d{1,2}:\d{2})"
)


def split_date_range_value(value: object) -> Optional[tuple[str, str]]:
    """把区间值切成 ``(start_str, end_str)``; 不是区间就返回 None。

    支持:
    - ``2025-08-25 17:01~2025-08-26 11:02``
    - ``2025-08-25~2025-08-26``
    - ``25/08/2025 - 26/08/2025``
    - ``2025-08-25 17:01 至 2025-08-26 11:02``
    - ``2025-08-18-15:01~2025-08-25-15:01``(Shopee 服务域周数据)
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    for separator in _RANGE_SEPARATORS:
        pattern = (
            rf"({_RANGE_DATE_TIME_PATTERN})\s*{separator}\s*({_RANGE_DATE_TIME_PATTERN})"
        )
        match = re.search(pattern, text)
        if match:
            start_str = _RANGE_DASH_TIME_CLEANUP.sub(r"\1 \2", match.group(1).strip())
            end_str = _RANGE_DASH_TIME_CLEANUP.sub(r"\1 \2", match.group(2).strip())
            return (start_str, end_str)

        pattern = rf"({_RANGE_DATE_PATTERN})\s*{separator}\s*({_RANGE_DATE_PATTERN})"
        match = re.search(pattern, text)
        if match:
            return (match.group(1).strip(), match.group(2).strip())

    return None
